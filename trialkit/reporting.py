"""把审核、编排和核定结果渲染为中文文本与可机读字典。"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum

from .model import REASON_TEXT, ReasonCode
from .terminology import Glossary
from .blinding import RunAudit
from .orchestration import PairPlan, counterbalance_summary
from .adjudication import AdjudicationReport


def _plain(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ReasonCode):
        return value.value
    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def to_plain(obj) -> dict:
    return _plain(obj)


def _reason_names(codes) -> str:
    names = [REASON_TEXT.get(code, code.value if isinstance(code, ReasonCode) else str(code)) for code in sorted(codes, key=lambda c: c.value)]
    return "、".join(names) if names else "无"


def render_glossary(glossary: Glossary) -> str:
    lines = ["== 共同术语与中性短写（可发参与者） =="]
    for alias, meaning in glossary.neutral_aliases.items():
        lines.append(f"- {alias}：{meaning}")
    for term in glossary.common_terms:
        lines.append(f"- {term.term}：{term.detail}（来源 {term.instruction_id}）")
    if glossary.warnings:
        lines.append("")
        lines.append("提示：")
        lines.extend(f"! {warning}" for warning in glossary.warnings)
    lines.append("")
    lines.append("内部映射（仅负责人/准备员）：" + "，".join(f"{k}->{v}" for k, v in glossary.internal_mapping.items()))
    return "\n".join(lines)


def render_audits(audits: dict[str, RunAudit]) -> str:
    lines = ["== 单次试用盲化/前提审核 =="]
    for run_id in sorted(audits):
        audit = audits[run_id]
        lines.append(f"[{run_id}] 实际累计所见：{'、'.join(audit.seen_materials) or '无'}")
        if not audit.findings and audit.prerequisites_available:
            lines.append("  审核通过：合并内容未泄漏分组，前置说明齐备")
        for finding in audit.findings:
            merged = f"（合并：{'、'.join(finding.combined_with)}）" if finding.combined_with else ""
            lines.append(f"  ! {finding.code.value}{merged}：{finding.explanation}")
        if not audit.prerequisites_available:
            lines.append("  ! PREMISE_MISMATCH：" + "；".join(audit.missing_prerequisites))
        if audit.remedies:
            for remedy in audit.remedies:
                covers = []
                if remedy.cover_marker:
                    covers.append("可加不影响操作的罩遮住表面标记")
                if remedy.recall_paper:
                    covers.append("纸本对照表可收回")
                lines.append(f"  补救（{remedy.asset_id}）：{'；'.join(covers) or '仅条件记录'}")
        if audit.escalate:
            lines.append("  >> 交试验负责人改变展示方法或暂缓该组")
    return "\n".join(lines)


def render_plans(plans: list[PairPlan], runs) -> str:
    lines = ["== 成对编排 =="]
    for plan in plans:
        pair = " + ".join(run.id for run in (plan.first, plan.second) if run)
        fixtures = " vs ".join(f for f in plan.fixtures if f)
        lines.append(
            f"[{plan.worker} / {plan.station}] {pair}（{fixtures}）"
            + ("；首件已锁定" if plan.locked_first else "")
        )
        lines.append(f"  原因：{_reason_names(plan.reason_codes)}")
        lines.extend(f"  - {note}" for note in plan.notes)
    summary = counterbalance_summary(plans)
    lines.append("")
    lines.append("顺序覆盖：" + "；".join(f"{k}×{v}" for k, v in summary["order_patterns"].items()))
    lines.append("两顺序均有覆盖：" + ("是" if summary["balanced"] else "否"))
    return "\n".join(lines)


def render_report(report: AdjudicationReport) -> str:
    lines = ["== 单件回报核定 =="]
    for run_id in sorted(report.verdicts):
        verdict = report.verdicts[run_id]
        lines.append(
            f"[{verdict.feedback_id} -> {run_id}] 做完：{'是' if verdict.completed else '否'}；"
            f"猜出分组：{'是' if verdict.guesses_group else '否'}；"
            f"针对本次夹具：{'是' if verdict.fixture_targeted else '否'}；"
            f"手感原话：{verdict.feel or '无明确方向'}"
        )
        lines.extend(f"  ! {flag}" for flag in verdict.flags)
        lines.extend(f"  · {text}" for text in verdict.explanations)
        if verdict.corrections:
            lines.append(f"  受后到更正影响：{'、'.join(verdict.corrections)}")

    lines.append("")
    lines.append("== 成对证据与研发汇总 ==")
    included = 0
    for evidence in report.pairs:
        status = "可比较，纳入汇总" if evidence.comparable else "不可比较，不入汇总"
        lines.append(
            f"[{evidence.worker} / {evidence.station}] "
            f"{evidence.first_run} + {evidence.second_run}：{status}"
        )
        lines.append(f"  原因：{_reason_names(evidence.reason_codes)}")
        if evidence.comparable:
            included += 1
            lines.append(f"  手感对比（原话）：{evidence.feel_comparison}")
        if evidence.reaudited_runs:
            lines.append(
                f"  后到更正重审：{'、'.join(evidence.reaudited_runs)}"
                f"（来源 {'、'.join(evidence.corrections)}）；"
                f"更正前结论：{'可比较' if evidence.comparable_before_correction else '不可比较'}"
            )
        if evidence.note:
            lines.append(f"  说明：{evidence.note}")
    lines.append(f"纳入研发汇总的对数：{included} / {len(report.pairs)}")
    if report.single_run_archive:
        lines.append("单件报告保留备查：" + "、".join(report.single_run_archive))

    lines.append("")
    lines.append("== 后到更正回查 ==")
    if not report.corrections:
        lines.append("无观察者更正")
    for correction in report.corrections:
        lines.append(
            f"{correction.feedback_id}：{correction.run_id} 第一组前实际见到 "
            f"{'、'.join(correction.extra_seen)}"
        )
    lines.append("重审试用：" + ("、".join(report.reaudited_runs) or "无"))
    lines.append("受影响配对（作业员）：" + ("、".join(report.affected_pairs) or "无"))
    return "\n".join(lines)
