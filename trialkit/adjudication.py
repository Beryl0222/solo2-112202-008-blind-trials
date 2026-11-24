"""试用回报核定与成对证据汇总。

核定原则（来自项目约束）：
- 从原话判断三件事：是否按有效前提做完、是否猜出分组、感受是否针对本次夹具；
- 例如“前次难推，后来这个轻，但我照师傅说的把卡位换了”不能直接算作
  本轮较好，因为夹持条件被改变，感受无法归因到本次夹具；
- 只有成对证据可供对比时才纳入研发汇总，单件报告仍保留备查；
- 后到人员说明某张对照表实际在第一组前看到，要回查哪些结论仍能采用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .blinding import audit_all
from .model import (
    Correction,
    Feedback,
    FeedbackVerdict,
    Instruction,
    PairEvidence,
    PairPlan,
    ReasonCode,
    Run,
    RunAudit,
    Asset,
)

# 停手/未完成的原话线索
INCOMPLETE_WORDS = ("停", "一半")
# 猜出分组的原话线索（看到标记后自述新件等）
GUESS_WORDS = ("知道是新件", "猜", "对照件")
# 非本次夹具的干扰因素：卡位被人调整、引用前次而非本次
CONFOUND_WORDS = ("换了卡位", "卡位换了", "前次", "师傅说")
TARGET_WORDS = ("这次夹具", "本次", "说的是夹具")
LIGHT_WORDS = ("轻",)
HARD_WORDS = ("难推", "费力", "沉")

CORRECTION_RE = re.compile(r"看到了\s*((?:I\d+(?:\s*[、,，]\s*)*)+)")


@dataclass
class AdjudicationReport:
    verdicts: dict[str, FeedbackVerdict]
    pairs: list[PairEvidence]
    corrections: list[Correction]
    reaudited_runs: tuple[str, ...]
    affected_pairs: tuple[str, ...]
    single_run_archive: tuple[str, ...]   # 单件报告，保留备查但不入汇总


def _detect_feel(text: str) -> str | None:
    hits = []
    if any(word in text for word in LIGHT_WORDS):
        hits.append("轻")
    if any(word in text for word in HARD_WORDS):
        hits.append("难推")
    return "/".join(hits) if hits else None


def parse_corrections(feedback: list[Feedback]) -> list[Correction]:
    """从观察者回报中解析“实际先看到某材料”的后到更正。"""
    corrections: list[Correction] = []
    for item in feedback:
        if not item.is_observer:
            continue
        match = CORRECTION_RE.search(item.text)
        if not match:
            continue
        ids = tuple(re.findall(r"I\d+", match.group(1)))
        corrections.append(
            Correction(
                feedback_id=item.id,
                run_id=item.run,
                extra_seen=ids,
                text=item.text,
                at=item.at,
            )
        )
    return corrections


def apply_corrections(
    runs: list[Run], corrections: list[Correction]
) -> dict[str, tuple[str, ...]]:
    """把更正并入该作业员在被更正试用及之后时点的累计所见。

    更正是对“第一组前实际看到”的补登记，因此对该作业员同工位、
    order 不小于被更正试用的所有试用生效。
    """
    run_by_id = {run.id: run for run in runs}
    overrides: dict[str, tuple[str, ...]] = {}
    for correction in corrections:
        target = run_by_id[correction.run_id]
        for run in runs:
            if run.worker != target.worker or run.station != target.station:
                continue
            if run.order < target.order:
                continue
            merged = {*run.seen, *correction.extra_seen}
            # 同时并入该作业员此前累计所见
            earlier = [r for r in runs if r.worker == run.worker and r.order < run.order]
            for earlier_run in earlier:
                merged.update(earlier_run.seen)
            overrides[run.id] = tuple(sorted(merged))
    return overrides


def adjudicate_feedback(
    item: Feedback,
    run: Run,
    audit: RunAudit,
    corrections_for_run: tuple[Correction, ...],
) -> FeedbackVerdict:
    """按原话核定单件回报。"""
    text = item.text
    flags: list[str] = []
    explanations: list[str] = []

    incomplete = any(word in text for word in INCOMPLETE_WORDS)
    if incomplete:
        flags.append("未按有效前提做完")
        explanations.append("原话出现中途停手描述：" + text)

    guesses = any(word in text for word in GUESS_WORDS)
    if guesses:
        flags.append("参与者据标记/措辞猜出分组")

    confound_hits = [word for word in CONFOUND_WORDS if word in text]
    explicit_target = any(word in text for word in TARGET_WORDS)
    # 没有干扰因素时，描述当前操作手感（推/握等）视为针对本次夹具；
    # 有干扰因素（换卡位、参照前次）时即便点名“夹具”也不能直接归因。
    if confound_hits:
        fixture_targeted = False
    elif explicit_target:
        fixture_targeted = True
    else:
        fixture_targeted = bool(re.search(r"推|握|摆", text))
    if confound_hits:
        flags.append("感受混入非本次夹具因素：" + "、".join(confound_hits))
        explanations.append(
            "夹持条件或参照对象发生变化，原话不能直接作为本轮夹具手感证据"
        )
    elif not fixture_targeted:
        explanations.append("原话未明确指向本次夹具，需谨慎归因")

    # 盲化审核发现会让“猜出分组”成立（即使原话没有明说）
    if audit.reason_codes and not guesses:
        guesses = True
        flags.append("盲化审核已判定该试用分组对参与者可推断")

    return FeedbackVerdict(
        feedback_id=item.id,
        run_id=run.id,
        completed=not incomplete,
        guesses_group=guesses,
        fixture_targeted=fixture_targeted,
        feel=_detect_feel(text),
        flags=flags,
        explanations=explanations,
        corrections=tuple(c.feedback_id for c in corrections_for_run),
    )


def build_pair_evidence(
    plan: PairPlan,
    runs: list[Run],
    verdicts: dict[str, FeedbackVerdict],
    audits: dict[str, RunAudit],
) -> PairEvidence:
    """把编排结果与单件核定合并成一对证据。"""
    run_by_id = {run.id: run for run in runs}
    member_runs = [run for run in (plan.first, plan.second) if run is not None]
    member_verdicts = [
        verdicts[run.id] for run in member_runs if run.id in verdicts
    ]

    reasons = set(plan.reason_codes)
    notes: list[str] = list(plan.notes)

    for run in member_runs:
        audit = audits.get(run.id)
        if audit:
            if not audit.prerequisites_available:
                reasons.add(ReasonCode.PREMISE_MISMATCH)
            # 所传审核可能已应用后到更正，其盲化原因要进入配对原因
            reasons.update(audit.reason_codes)
        verdict = verdicts.get(run.id)
        if verdict is None:
            reasons.add(ReasonCode.INCOMPLETE_PAIR)
            continue
        if verdict.guesses_group:
            reasons.add(ReasonCode.GUESS_GROUP)
        if not verdict.fixture_targeted:
            reasons.add(ReasonCode.FEEDBACK_CONFOUND)
        if not verdict.completed:
            reasons.add(ReasonCode.PREMISE_MISMATCH)

    if not plan.structurally_complete:
        reasons.add(ReasonCode.INCOMPLETE_PAIR)

    comparable = not reasons and len(member_verdicts) == 2 and all(
        v.completed and v.fixture_targeted and not v.guesses_group for v in member_verdicts
    )
    if not comparable and not notes:
        notes.append("存在不可消除原因，详见 reason_codes")

    return PairEvidence(
        worker=plan.worker,
        station=plan.station,
        first_run=plan.first.id if plan.first else None,
        second_run=plan.second.id if plan.second else None,
        comparable=comparable,
        reason_codes=reasons,
        verdicts=member_verdicts,
        note="；".join(notes),
    )


def _verdict_map(runs, feedback, audits, corrections_by_run):
    feedback_by_run: dict[str, list[Feedback]] = {}
    for item in feedback:
        feedback_by_run.setdefault(item.run, []).append(item)
    verdicts: dict[str, FeedbackVerdict] = {}
    for run in runs:
        participant_items = [f for f in feedback_by_run.get(run.id, []) if not f.is_observer]
        for item in participant_items:
            verdicts[run.id] = adjudicate_feedback(
                item,
                run,
                audits[run.id],
                tuple(corrections_by_run.get(run.id, ())),
            )
    return verdicts


def adjudicate(
    runs: list[Run],
    instructions: list[Instruction],
    feedback: list[Feedback],
    assets: list[Asset],
    plans: list[PairPlan],
) -> AdjudicationReport:
    """完整核定：应用后到更正、重审、逐件核定并汇总成对证据。"""
    corrections = parse_corrections(feedback)
    overrides = apply_corrections(runs, corrections)
    reaudited = tuple(sorted(overrides))

    corrections_by_run: dict[str, list[Correction]] = {}
    for correction in corrections:
        corrections_by_run.setdefault(correction.run_id, []).append(correction)

    # 先按“登记所见”核定一遍，作为更正前基线，用于回查被推翻的结论
    base_audits = audit_all(runs, instructions, assets)
    base_verdicts = _verdict_map(runs, feedback, base_audits, corrections_by_run)
    base_pairs = {
        (plan.worker, plan.station): build_pair_evidence(
            plan, runs, base_verdicts, base_audits
        )
        for plan in plans
    }

    # 再按更正后的实际所见重审
    audits = audit_all(runs, instructions, assets, seen_override=overrides or None)
    verdicts = _verdict_map(runs, feedback, audits, corrections_by_run)

    pairs = []
    for plan in plans:
        evidence = build_pair_evidence(plan, runs, verdicts, audits)
        member_ids = tuple(
            run_id for run_id in (evidence.first_run, evidence.second_run) if run_id
        )
        evidence.reaudited_runs = tuple(run_id for run_id in member_ids if run_id in reaudited)
        evidence.corrections = tuple(
            c.feedback_id
            for c in corrections
            if c.run_id in member_ids
        )
        baseline = base_pairs[(plan.worker, plan.station)]
        evidence.comparable_before_correction = baseline.comparable
        if evidence.reaudited_runs and baseline.comparable != evidence.comparable:
            evidence.note = (
                f"后到更正改变结论：更正前“{'可比较' if baseline.comparable else '不可比较'}”，"
                f"更正后“{'可比较' if evidence.comparable else '不可比较'}”；"
                + evidence.note
            ).rstrip("；")
        pairs.append(evidence)

    affected = tuple(
        evidence.worker for evidence in pairs if evidence.reaudited_runs
    )
    paired_run_ids = {
        run_id
        for evidence in pairs
        for run_id in (evidence.first_run, evidence.second_run)
        if run_id
    }
    archived = tuple(
        run.id for run in runs if run.id in verdicts and run.id not in paired_run_ids
    )

    return AdjudicationReport(
        verdicts=verdicts,
        pairs=pairs,
        corrections=corrections,
        reaudited_runs=reaudited,
        affected_pairs=affected,
        single_run_archive=archived,
    )
