"""从自然语言草稿和零件描述中辨认操作对象、顺序、代称与前置条件。

资料里同一措辞可能指向不同对象（“短柄”既可能是待比较夹具，也可能是
两组共用的扳手），本模块只做辨认和中性术语整理，不修改来件措辞。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .model import (
    Glossary,
    Instruction,
    TermKind,
    TermUse,
)

# 零件编号，例如 K2、K3
FIXTURE_RE = re.compile(r"K\d+")
# 共同工具：两组都使用、不参与比较
SHARED_TOOL_WORDS = ("扳手",)
# 工艺标记：只有准备人员应当掌握的身份线索
MARKER_WORDS = ("凹点", "标记表", "打凹点", "表面标记")
# 停手条件与前置动作的提示词
STOP_WORDS = ("停",)
PREREQ_WORDS = ("先", "确认", "准备", "前置")
CLAUSE_SPLIT_RE = re.compile(r"[。；;]")


@dataclass
class InstructionPrep:
    """单张说明中辨认出的动作结构。"""

    instruction_id: str
    prerequisites: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    actions: tuple[str, ...]


def _classify_term(term: str, context: str, instruction_id: str) -> TermUse:
    """根据术语所在上下文判断归属。"""
    if FIXTURE_RE.fullmatch(term):
        return TermUse(term, TermKind.FIXTURE, instruction_id, "零件编号")
    if term in MARKER_WORDS:
        return TermUse(term, TermKind.MARKER, instruction_id, "工艺标记线索")
    if term in SHARED_TOOL_WORDS:
        return TermUse(term, TermKind.SHARED_TOOL, instruction_id, "两组共用工具")
    # “短柄”消歧：紧跟夹具/扳手时归属不同；单独出现则保持歧义并告警
    if term == "短柄":
        if "短柄夹具" in context:
            return TermUse(term, TermKind.FIXTURE, instruction_id, "短柄夹具的简称")
        if "短柄扳手" in context:
            return TermUse(term, TermKind.SHARED_TOOL, instruction_id, "短柄扳手的简称")
        return TermUse(term, TermKind.COMMON, instruction_id, "裸用“短柄”，夹具/扳手歧义")
    return TermUse(term, TermKind.COMMON, instruction_id, "共同动作术语")


def extract_term_uses(instructions: list[Instruction]) -> list[TermUse]:
    """逐张说明辨认术语及其归属，保留来源说明编号。"""
    uses: list[TermUse] = []
    for inst in instructions:
        text = inst.text
        for match in FIXTURE_RE.finditer(text):
            uses.append(_classify_term(match.group(), text, inst.id))
        for word in (*SHARED_TOOL_WORDS, *MARKER_WORDS):
            start = 0
            while (index := text.find(word, start)) >= 0:
                uses.append(_classify_term(word, text, inst.id))
                start = index + len(word)
        # “短柄”需要单独扫描，且与“短柄夹具/短柄扳手”的出现分别登记
        for match in re.finditer(r"短柄(?:夹具|扳手)?", text):
            phrase = match.group()
            if phrase == "短柄夹具":
                uses.append(TermUse("短柄", TermKind.FIXTURE, inst.id, "短柄夹具的简称"))
            elif phrase == "短柄扳手":
                uses.append(TermUse("短柄", TermKind.SHARED_TOOL, inst.id, "短柄扳手的简称"))
            else:
                uses.append(_classify_term("短柄", text, inst.id))
    # 去重（同说明同术语同归属只留一条），保持稳定顺序
    unique: dict[tuple, TermUse] = {}
    for use in uses:
        unique.setdefault((use.instruction_id, use.term, use.kind), use)
    return list(unique.values())


def extract_instruction_prep(instruction: Instruction) -> InstructionPrep:
    """辨认一张说明里的前置动作、停手条件和其余动作。"""
    prereqs: list[str] = []
    stops: list[str] = []
    actions: list[str] = []
    for raw in CLAUSE_SPLIT_RE.split(instruction.text):
        clause = raw.strip()
        if not clause:
            continue
        if any(word in clause for word in STOP_WORDS):
            stops.append(clause)
        elif any(word in clause for word in PREREQ_WORDS):
            prereqs.append(clause)
        else:
            actions.append(clause)
    return InstructionPrep(instruction.id, tuple(prereqs), tuple(stops), tuple(actions))


def extract_all_preps(instructions: list[Instruction]) -> dict[str, InstructionPrep]:
    return {inst.id: extract_instruction_prep(inst) for inst in instructions}


def prep_only_instructions(instructions: list[Instruction]) -> list[Instruction]:
    """只允许准备人员知道的信息。"""
    return [inst for inst in instructions if inst.prep_only]


def find_ambiguous_terms(uses: list[TermUse]) -> list[TermUse]:
    """找出归属仍有歧义、必须在共同术语中消歧的术语。"""
    ambiguous = []
    for use in uses:
        if use.term == "短柄" and use.detail.startswith("裸用"):
            ambiguous.append(use)
    return ambiguous


def build_glossary(instructions: list[Instruction]) -> Glossary:
    """生成可发给参与者的共同术语与不泄漏分组的短写。

    - 中性短写（夹具甲/夹具乙）只在内部映射真实编号；
    - 共同工具与动作术语直接给出消歧后的写法；
    - 工艺标记不进入参与者版术语表。
    """
    uses = extract_term_uses(instructions)
    fixtures = sorted({u.term for u in uses if u.kind is TermKind.FIXTURE and FIXTURE_RE.fullmatch(u.term)})

    neutral_aliases: dict[str, str] = {}
    internal_mapping: dict[str, str] = {}
    alias_labels = ("夹具甲", "夹具乙", "夹具丙", "夹具丁")
    for label, fixture in zip(alias_labels, fixtures):
        neutral_aliases[label] = "本轮试用夹具之一（身份由准备员掌握）"
        internal_mapping[label] = fixture

    common_terms = [u for u in uses if u.kind in (TermKind.SHARED_TOOL, TermKind.COMMON)]

    warnings: list[str] = []
    for use in find_ambiguous_terms(uses):
        warnings.append(
            f"{use.instruction_id} 中“短柄”未带夹具/扳手后缀，"
            "参与者版材料须统一写成“短柄扳手”或中性夹具短写"
        )
    marker_sources = sorted({
        u.instruction_id
        for u in uses
        if u.kind is TermKind.MARKER
        and u.instruction_id not in {i.id for i in prep_only_instructions(instructions)}
    })
    if marker_sources:
        warnings.append(
            "工艺标记线索出现在 " + "、".join(marker_sources) +
            "；是否泄漏需在 blinding 模块按实际分发对象与合并内容审核"
        )

    return Glossary(
        common_terms=common_terms,
        neutral_aliases=neutral_aliases,
        internal_mapping=internal_mapping,
        warnings=warnings,
    )
