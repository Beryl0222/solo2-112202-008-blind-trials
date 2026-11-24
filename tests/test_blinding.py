"""盲化审核测试：按实际见到的合并内容判断，而非逐张判断。"""
import bootstrap  # noqa: F401  隔离模式路径引导
import unittest

from trialkit.blinding import (
    audit_all,
    cumulative_seen,
    is_marker_table,
    parse_remedies,
    station_trained_workers,
)
from trialkit.loading import load
from trialkit.model import ReasonCode


class BlindingTest(unittest.TestCase):
    def setUp(self):
        self.data = load()
        self.runs = self.data["runs"]
        self.instructions = self.data["instructions"]
        self.assets = self.data["assets"]
        self.audits = audit_all(self.runs, self.instructions, self.assets)

    def test_marker_table_detected(self):
        by_id = {i.id: i for i in self.instructions}
        self.assertTrue(is_marker_table(by_id["I4"]))
        self.assertFalse(is_marker_table(by_id["I2"]))
        # 准备员专有的 I1 不参与参与者审核
        self.assertFalse(is_marker_table(by_id["I1"]))

    def test_cumulative_seen_merges_materials(self):
        seen = cumulative_seen(self.runs)
        # R2 时点应包含 R1 已见的 I4
        self.assertEqual(set(seen["R2"]), {"I2", "I3", "I4"})
        self.assertEqual(set(seen["R1"]), {"I2", "I4"})

    def test_marker_table_plus_physical_fixture_leaks(self):
        # 向在 R1 已见 I4，K3 有凹点可被推断
        r1 = self.audits["R1"]
        self.assertIn(ReasonCode.MARKER_REVEAL, r1.reason_codes)
        # K2 无凹点同样可推断，R2 也泄漏
        self.assertIn(ReasonCode.MARKER_REVEAL, self.audits["R2"].reason_codes)

    def test_materials_alone_do_not_leak(self):
        # 沈登记所见只有 I2，单张无型号信息，审核通过
        self.assertTrue(self.audits["R3"].clean)
        self.assertTrue(self.audits["R4"].clean)

    def test_remedies_parsed_per_station(self):
        remedies = parse_remedies(self.assets)
        west, east = remedies["西台"], remedies["东台"]
        self.assertTrue(any(r.recall_paper for r in west))
        self.assertTrue(any(r.cover_marker for r in east))

    def test_training_gate(self):
        trained = station_trained_workers(self.assets)
        self.assertEqual(trained["东台"], frozenset({"郝"}))
        # 西台未限制时不产生条目
        self.assertNotIn("西台", trained)

    def test_recall_remedy_avoids_escalation_for_marker_leak(self):
        # 西台可收回纸本 I4，因此标记泄漏有补救，不升级
        self.assertFalse(self.audits["R1"].escalate)
        self.assertFalse(self.audits["R2"].escalate)

    def test_direct_identity_text_escalates(self):
        # 构造一张参与者可见、直接点名型号的说明，必须升级为暂缓/改展示
        from trialkit.model import Instruction, Run, Phase
        instructions = [
            *self.instructions,
            Instruction("IX", "试用员", (), "K3 是新夹具，与 K2 对照"),
        ]
        runs = [
            Run("RX", "向", 1, "西台", "K3", ("IX",), Phase.PLANNED),
        ]
        audits = audit_all(runs, instructions, self.assets)
        self.assertIn(ReasonCode.TEXT_LEAK, audits["RX"].reason_codes)
        self.assertTrue(audits["RX"].escalate)

    def test_missing_prerequisite_blocks_run(self):
        # I3 声明 ref=I2；只发 I3 时前置不可得
        from trialkit.model import Run, Phase
        runs = [Run("RX", "向", 1, "西台", "K2", ("I3",), Phase.PLANNED)]
        audits = audit_all(runs, self.instructions, self.assets)
        self.assertFalse(audits["RX"].prerequisites_available)
        self.assertTrue(audits["RX"].escalate)


if __name__ == "__main__":
    unittest.main()
