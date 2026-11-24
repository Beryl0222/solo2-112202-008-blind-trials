"""术语辨认与共同术语测试：同一措辞“短柄”的两种归属。"""
import bootstrap  # noqa: F401  隔离模式路径引导
import unittest

from trialkit.loading import load
from trialkit.model import TermKind
from trialkit.terminology import (
    build_glossary,
    extract_all_preps,
    extract_term_uses,
    find_ambiguous_terms,
    prep_only_instructions,
)


class TerminologyTest(unittest.TestCase):
    def setUp(self):
        self.data = load()
        self.instructions = self.data["instructions"]

    def test_short_handle_disambiguates_fixture_vs_wrench(self):
        uses = extract_term_uses(self.instructions)
        kinds = {(u.term, u.kind, u.instruction_id) for u in uses}
        # I2“短柄扳手”必须辨认为共用工具
        self.assertIn(("短柄", TermKind.SHARED_TOOL, "I2"), kinds)
        # I1“短柄夹具”必须辨认为待比较夹具
        self.assertIn(("短柄", TermKind.FIXTURE, "I1"), kinds)

    def test_fixture_codes_and_markers_classified(self):
        uses = extract_term_uses(self.instructions)
        fixture_terms = {u.term for u in uses if u.kind is TermKind.FIXTURE}
        self.assertEqual({"K2", "K3", "短柄"}, fixture_terms)
        marker_sources = {u.instruction_id for u in uses if u.kind is TermKind.MARKER}
        self.assertIn("I4", marker_sources)  # 对照表
        self.assertIn("I1", marker_sources)  # 准备员专有说明里的凹点描述

    def test_prep_only_isolated(self):
        prep_only = {inst.id for inst in prep_only_instructions(self.instructions)}
        self.assertEqual(prep_only, {"I1"})

    def test_glossary_aliases_hide_group_identity(self):
        glossary = build_glossary(self.instructions)
        self.assertEqual(set(glossary.neutral_aliases), {"夹具甲", "夹具乙"})
        # 中性短写的参与者释义不出现真实型号
        for meaning in glossary.neutral_aliases.values():
            self.assertNotIn("K2", meaning)
            self.assertNotIn("K3", meaning)
        # 内部映射保留真实指向，仅供负责人
        self.assertEqual(glossary.internal_mapping["夹具甲"], "K2")
        self.assertEqual(glossary.internal_mapping["夹具乙"], "K3")
        # 参与者版警告不得引用准备员专有说明 I1
        self.assertTrue(all("I1" not in w for w in glossary.warnings))

    def test_prerequisites_and_stop_conditions_extracted(self):
        preps = extract_all_preps(self.instructions)
        self.assertTrue(preps["I2"].prerequisites)  # 先确认托面齐平
        self.assertTrue(any("停" in c for c in preps["I3"].stop_conditions))

    def test_no_bare_ambiguous_short_handle_in_pack(self):
        # 当前资料包的“短柄”均带后缀；若出现裸用必须被登记为歧义
        ambiguous = find_ambiguous_terms(extract_term_uses(self.instructions))
        self.assertEqual(ambiguous, [])


if __name__ == "__main__":
    unittest.main()
