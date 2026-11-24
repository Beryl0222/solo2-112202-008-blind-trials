"""成对编排测试：锁定、补齐、训练门槛与顺序平衡。"""
import bootstrap  # noqa: F401  隔离模式路径引导
import unittest

from trialkit import orchestration
from trialkit.blinding import audit_all
from trialkit.loading import load
from trialkit.model import (
    Asset,
    Instruction,
    PairPlan,
    Phase,
    ReasonCode,
    Run,
)


class OrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.data = load()
        self.audits = audit_all(
            self.data["runs"], self.data["instructions"], self.data["assets"]
        )
        self.plans = orchestration.build_pairs(
            self.data["runs"], self.audits, self.data["assets"]
        )
        self.plan_by_worker = {p.worker: p for p in self.plans}

    def test_pairs_cover_same_station_and_both_fixtures(self):
        for plan in self.plans:
            self.assertTrue(plan.structurally_complete)
            self.assertTrue(plan.counterbalanced)
            self.assertEqual(plan.first.station, plan.second.station)

    def test_started_first_runs_are_locked(self):
        locked = {run.id for run in orchestration.locked_runs(self.data["runs"])}
        self.assertEqual(locked, {"R1", "R3", "R4"})
        for worker in ("向", "沈"):
            self.assertTrue(self.plan_by_worker[worker].locked_first)

    def test_marker_leak_propagates_to_xiang_pair_only(self):
        self.assertIn(ReasonCode.MARKER_REVEAL, self.plan_by_worker["向"].reason_codes)
        self.assertNotIn(ReasonCode.MARKER_REVEAL, self.plan_by_worker["沈"].reason_codes)
        self.assertNotIn(ReasonCode.MARKER_REVEAL, self.plan_by_worker["郝"].reason_codes)

    def test_counterbalance_both_orders_present(self):
        summary = orchestration.counterbalance_summary(self.plans)
        self.assertTrue(summary["balanced"])
        self.assertIn("K3->K2", summary["order_patterns"])
        self.assertIn("K2->K3", summary["order_patterns"])

    def test_untrained_worker_is_premise_mismatch(self):
        runs = [
            Run("T1", "向", 1, "东台", "K2", ("I2",), Phase.PLANNED),
            Run("T2", "向", 2, "东台", "K3", ("I5",), Phase.PLANNED),
        ]
        audits = audit_all(runs, self.data["instructions"], self.data["assets"])
        plans = orchestration.build_pairs(runs, audits, self.data["assets"])
        self.assertIn(ReasonCode.PREMISE_MISMATCH, plans[0].reason_codes)

    def test_incomplete_pair_can_be_completed_on_west_station(self):
        runs = [Run("T1", "郝", 1, "西台", "K2", ("I2",), Phase.DONE)]
        audits = audit_all(runs, self.data["instructions"], self.data["assets"])
        plans = orchestration.build_pairs(runs, audits, self.data["assets"])
        plan = plans[0]
        self.assertIn(ReasonCode.INCOMPLETE_PAIR, plan.reason_codes)
        self.assertNotIn(ReasonCode.NO_FEASIBLE_PAIR, plan.reason_codes)
        option = orchestration.completion_option(plan, self.data["assets"])
        self.assertTrue(option.feasible)
        self.assertEqual(option.fixture, "K3")

    def test_east_station_swap_blocked_this_shift_marks_no_feasible(self):
        # 东台限制“同类调换需要下个班”：当前班次补做受阻
        runs = [Run("T1", "郝", 1, "东台", "K2", ("I2",), Phase.DONE)]
        audits = audit_all(runs, self.data["instructions"], self.data["assets"])
        plans = orchestration.build_pairs(runs, audits, self.data["assets"])
        self.assertIn(ReasonCode.NO_FEASIBLE_PAIR, plans[0].reason_codes)
        option = orchestration.completion_option(plans[0], self.data["assets"])
        self.assertFalse(option.feasible)

    def test_other_complete_pairs_continue_when_one_pair_fails(self):
        # 向的对不可比较时，沈的对仍然作为完整对保留
        failing = self.plan_by_worker["向"]
        self.assertTrue(failing.reason_codes)
        surviving = self.plan_by_worker["沈"]
        self.assertTrue(surviving.structurally_complete)

    def test_reason_categories_are_distinguishable(self):
        all_codes = set()
        for plan in self.plans:
            all_codes.update(plan.reason_codes)
        # 三类原因在数据中至少各有结构上的体现
        self.assertIn(ReasonCode.MARKER_REVEAL, all_codes)  # 文字/标记泄漏
        # 构造前提不同与凑不出配对
        bad_runs = [Run("T1", "向", 1, "东台", "K2", ("I2",), Phase.DONE)]
        bad_audits = audit_all(bad_runs, self.data["instructions"], self.data["assets"])
        bad_plans = orchestration.build_pairs(bad_runs, bad_audits, self.data["assets"])
        self.assertIn(ReasonCode.NO_FEASIBLE_PAIR, bad_plans[0].reason_codes)


if __name__ == "__main__":
    unittest.main()
