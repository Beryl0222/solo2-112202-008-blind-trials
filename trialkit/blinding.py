"""盲化泄漏审核。

审核原则（来自项目约束）：
1. 只按参与者实际见到的材料判断；准备员专有说明不进入参与者视野。
2. 单独看不出型号的两张材料，连同参与者已看到的对照表合并后可能泄漏，
   因此按“该时点累计实际见到的合并内容”判断，而不是逐张判断。
3. 若按说明执行需要用到会揭晓身份的工艺标记，应登记为泄漏，并交试验
   负责人改变展示方法或暂缓该组。
4. 本模块只做审核与建议，不直接控制机器或改写分发记录。
"""
from __future__ import annotations

import re

from .model import (
    Instruction,
    LeakFinding,
    ReasonCode,
    Run,
    RunAudit,
    StationRemedy,
    Asset,
)
from .terminology import MARKER_WORDS

# 准备员专有说明中给出的真实身份知识：型号 -> 可观察到的工艺标记状态
# 该知识只用于审核推断链，不会写进给参与者的材料。
FIXTURE_MARKER_STATE = {
    "K3": "柄上有凹点",
    "K2": "柄上无凹点",
}
CONTROL_WORDS = ("对照",)
TRAINING_RE = re.compile(r"只有(.+?)完成本台训练")


def is_marker_table(instruction: Instruction) -> bool:
    """该说明是否是把工艺标记与新旧/分组对应起来的对照表。"""
    if not instruction.participant_visible:
        return False
    return "标记表" in instruction.text or (
        any(word in instruction.text for word in MARKER_WORDS)
        and ("新件" in instruction.text or "统一" in instruction.text)
    )


def direct_identity_leak(instruction: Instruction, fixture: str) -> bool:
    """说明文字是否直接点出本次夹具型号或其对照身份。"""
    if not instruction.participant_visible:
        return False
    if fixture in instruction.text:
        return True
    if all(word in instruction.text for word in CONTROL_WORDS):
        # 出现“对照”且与夹具编号同句，属于直接揭晓分组
        return bool(re.search(r"K\d+", instruction.text))
    return False


def parse_remedies(assets: list[Asset]) -> dict[str, list[StationRemedy]]:
    """从设备台记录中解析准备人员可执行的展示补救措施。"""
    result: dict[str, list[StationRemedy]] = {}
    for asset in assets:
        remedy = StationRemedy(
            station=asset.station,
            asset_id=asset.id,
            cover_marker="罩遮" in asset.limits,
            recall_paper="收回" in asset.limits,
            note=asset.limits,
        )
        result.setdefault(asset.station, []).append(remedy)
    return result


def station_trained_workers(assets: list[Asset]) -> dict[str, frozenset[str]]:
    """解析各工位已完成本台训练的作业员；未注明则不限制。"""
    trained: dict[str, frozenset[str]] = {}
    for asset in assets:
        match = TRAINING_RE.search(asset.limits)
        if match:
            trained[asset.station] = frozenset(match.group(1).split("、"))
    return trained


def cumulative_seen(runs: list[Run]) -> dict[str, tuple[str, ...]]:
    """每名作业员在各次试用开始时点累计实际见到的材料。"""
    seen_by_worker: dict[str, set[str]] = {}
    result: dict[str, tuple[str, ...]] = {}
    for run in sorted(runs, key=lambda r: (r.worker, r.order)):
        bag = seen_by_worker.setdefault(run.worker, set())
        bag.update(run.seen)
        result[run.id] = tuple(sorted(bag))
    return result


def audit_run(
    run: Run,
    instructions: list[Instruction],
    cumulative: dict[str, tuple[str, ...]],
    remedies_by_station: dict[str, list[StationRemedy]],
) -> RunAudit:
    """审核单次试用在其开始时点的盲化与前置说明可行性。"""
    by_id = {inst.id: inst for inst in instructions}
    seen_ids = cumulative[run.id]
    seen_instructions = [by_id[s] for s in seen_ids if s in by_id]
    marker_tables = [inst for inst in seen_instructions if is_marker_table(inst)]
    findings: list[LeakFinding] = []

    for inst in seen_instructions:
        if direct_identity_leak(inst, run.fixture):
            findings.append(
                LeakFinding(
                    instruction_id=inst.id,
                    code=ReasonCode.TEXT_LEAK,
                    explanation=(
                        f"{inst.id} 的文字直接出现 {run.fixture} 或对照身份，"
                        "参与者据此可知分组"
                    ),
                )
            )

    if marker_tables:
        # 对照表把“有无凹点”对应到新旧件；实物上 K3 有凹点、K2 无凹点，
        # 两组成员都能被推断，必须按合并内容判泄漏。
        combined = tuple(inst.id for inst in marker_tables)
        state = FIXTURE_MARKER_STATE.get(run.fixture)
        findings.append(
            LeakFinding(
                instruction_id=combined[0],
                code=ReasonCode.MARKER_REVEAL,
                explanation=(
                    "已见对照表 " + "、".join(combined)
                    + f"；本次实物（{run.fixture}，{state}）的标记状态可推断其新旧/分组身份"
                ),
                combined_with=combined,
            )
        )

    # 前置说明：声明的 ref 必须在累计所见内，先备说明与盲法要同时可行
    missing: list[str] = []
    for inst in seen_instructions:
        for ref in inst.ref:
            if ref not in seen_ids:
                missing.append(f"{inst.id} 要求先见 {ref}")
    prereq_ok = not missing

    remedies = remedies_by_station.get(run.station, [])
    # 判断补救是否覆盖发现：遮罩/收回只对工艺标记类泄漏有效
    marker_finding = any(f.code is ReasonCode.MARKER_REVEAL for f in findings)
    direct_finding = any(f.code is ReasonCode.TEXT_LEAK for f in findings)
    remedy_covers_marker = any(r.cover_marker or r.recall_paper for r in remedies)
    escalate = False
    if direct_finding:
        escalate = True  # 直接点名型号只能换展示文案/暂缓，设备台措施无法覆盖
    if marker_finding and not remedy_covers_marker:
        escalate = True
    if not prereq_ok:
        escalate = True  # 先备说明无法满足时，该组应暂缓

    return RunAudit(
        run_id=run.id,
        seen_materials=seen_ids,
        findings=findings,
        prerequisites_available=prereq_ok,
        missing_prerequisites=tuple(missing),
        remedies=remedies,
        escalate=escalate,
    )


def audit_all(
    runs: list[Run],
    instructions: list[Instruction],
    assets: list[Asset],
    seen_override: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, RunAudit]:
    """对全部试用做审核；seen_override 用于后到更正后的回查。"""
    cumulative = cumulative_seen(runs)
    if seen_override:
        cumulative = {**cumulative, **seen_override}
    remedies_by_station = parse_remedies(assets)
    return {
        run.id: audit_run(run, instructions, cumulative, remedies_by_station)
        for run in runs
    }
