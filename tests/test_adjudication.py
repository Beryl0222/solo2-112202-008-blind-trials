"""回报核定、成对证据与后到更正回查测试。"""
import bootstrap  # noqa: F401  隔离模式路径引导
import unittest

from trialkit.adjudication import (
    adjudicate,
    apply_corrections,
    parse_corrections,
)
from trialkit.blinding import audit_all
from trialkit import orchestration
from trialkit.loading import load
from trialkit.model import ReasonCode


class AdjudicationTest(unittest.TestCase):
    def setUp(self):
        self.data = load()
        self.audits = audit_all(
            self.data["runs"], self.data["instructions"], self.data["assets"]
        )
        self.plans = orchestration.build_pairs(
            self.data["runs"], self.audits, self.data["assets"]
        )
        self.report = adjudicate(
            self.data["runs"],
            self.data["instructions"],
            self.data["feedback"],
            self.data["assets"],
            self.plans,
        )

    def test_correction_parsed_and_propagated_to_later_runs(self):
        corrections = parse_corrections(self.data["feedback"])
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0].extra_seen, ("I4",))
        overrides = apply_corrections(self.data["runs"], corrections)
        # R3 与同工位后续 R4 都被并入 I4
        self.assertIn("I4", overrides["R3"])
        self.assertIn("I4", overrides["R4"])
        # 其他作业员不受影响
        self.assertNotIn("R1", overrides)

    def test_reaudit_marks_shen_pair_and_names_affected_runs(self):
        self.assertEqual(set(self.report.reaudited_runs), {"R3", "R4"})
        self.assertIn("沈", self.report.affected_pairs)

    def test_f1_completed_but_group_guessed(self):
        verdict = self.report.verdicts["R1"]
        self.assertTrue(verdict.completed)
        self.assertTrue(verdict.guesses_group)
        self.assertTrue(verdict.fixture_targeted)  # “推起来轻”描述的是本次
        self.assertEqual(verdict.feel, "轻")

    def test_f2_incomplete_and_targeted(self):
        verdict = self.report.verdicts["R3"]
        self.assertFalse(verdict.completed)       # 推到一半停
        self.assertTrue(verdict.fixture_targeted)  # “难推的是这次夹具”
        self.assertEqual(verdict.feel, "难推")
        self.assertIn("F4", verdict.corrections)

    def test_f3_confounded_not_counted_as_better(self):
        verdict = self.report.verdicts["R4"]
        self.assertFalse(verdict.fixture_targeted)  # 换了卡位，不能归因本轮
        self.assertTrue(any("非本次夹具因素" in flag for flag in verdict.flags))

    def test_no_pair_enters_summary_without_pairwise_evidence(self):
        self.assertTrue(all(not p.comparable for p in self.report.pairs))
        comparable = [p for p in self.report.pairs if p.comparable]
        self.assertEqual(comparable, [])

    def test_shen_pair_invalid_for_multiple_distinct_reasons(self):
        shen = next(p for p in self.report.pairs if p.worker == "沈")
        codes = shen.reason_codes
        self.assertIn(ReasonCode.GUESS_GROUP, codes)
        self.assertIn(ReasonCode.FEEDBACK_CONFOUND, codes)
        self.assertIn(ReasonCode.PREMISE_MISMATCH, codes)
        self.assertEqual(shen.reaudited_runs, ("R3", "R4"))

    def test_xiang_pair_carries_marker_and_incomplete_reasons(self):
        xiang = next(p for p in self.report.pairs if p.worker == "向")
        self.assertIn(ReasonCode.MARKER_REVEAL, xiang.reason_codes)
        self.assertIn(ReasonCode.INCOMPLETE_PAIR, xiang.reason_codes)

    def test_hao_pair_only_incomplete_no_blinding_finding(self):
        hao = next(p for p in self.report.pairs if p.worker == "郝")
        self.assertEqual(hao.reason_codes, {ReasonCode.INCOMPLETE_PAIR})

    def test_single_run_reports_kept_for_archive(self):
        # 所有有回报的试用即使不入汇总也保留在 verdicts 中
        self.assertEqual(set(self.report.verdicts), {"R1", "R3", "R4"})

    def test_correction_flips_a_formerly_comparable_pair(self):
        # 构造一组在“登记所见”下可比较、加入 I4 更正后变不可比较的数据
        from trialkit.model import Feedback, Phase, Run
        runs = [
            Run("Q1", "郝", 1, "东台", "K2", ("I2",), Phase.DONE),
            Run("Q2", "郝", 2, "东台", "K3", ("I5",), Phase.DONE),
        ]
        feedback = [
            Feedback("G1", "Q1", "2026-10-22T09:00", "郝", "这次夹具推起来稳。"),
            Feedback("G2", "Q2", "2026-10-22T09:30", "郝", "这次夹具推起来轻。"),
            Feedback("G3", "Q1", "2026-10-22T10:00", "观察者", "更正，郝在第一件前还看到了 I4，有签名。"),
        ]
        audits = audit_all(runs, self.data["instructions"], self.data["assets"])
        plans = orchestration.build_pairs(runs, audits, self.data["assets"])
        report = adjudicate(
            runs, self.data["instructions"], feedback, self.data["assets"], plans
        )
        pair = report.pairs[0]
        self.assertFalse(pair.comparable)
        self.assertTrue(pair.comparable_before_correction)
        self.assertIn(ReasonCode.MARKER_REVEAL, pair.reason_codes)


if __name__ == "__main__":
    unittest.main()
