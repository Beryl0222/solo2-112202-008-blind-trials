"""成对试用编排。

编排约束（来自项目约束）：
- 在每位作业员、实际训练和可用夹具之间安排成对试用；
- 两款夹具尽量拥有相同工位、相同夹持条件，且在不同作业员之间顺序相反；
- 已真实开始（已做）的第一件不能重新排序；
- 后续可用满足相同约束的对照补齐，否则把该人的配对标为不可比较，
  其他完整对仍可继续；
- 原因必须可区分为文字说明泄漏、动作前提不同、确实凑不出有效配对。
"""
from __future__ import annotations

from dataclasses import dataclass

from .blinding import RunAudit, parse_remedies, station_trained_workers
from .model import (
    Asset,
    BLINDING_REASONS,
    PairPlan,
    ReasonCode,
    Run,
)

COMPARED_FIXTURES = ("K2", "K3")


@dataclass
class CompletionOption:
    """为未完成配对建议的补齐试用。"""

    worker: str
    station: str
    fixture: str
    order: int
    feasible: bool
    blockers: tuple[str, ...]


def _group_runs(runs: list[Run]) -> dict[tuple[str, str], list[Run]]:
    grouped: dict[tuple[str, str], list[Run]] = {}
    for run in runs:
        grouped.setdefault((run.worker, run.station), []).append(run)
    for key in grouped:
        grouped[key].sort(key=lambda r: r.order)
    return grouped


def build_pairs(
    runs: list[Run],
    audits: dict[str, RunAudit],
    assets: list[Asset],
) -> list[PairPlan]:
    """按作业员+工位组装配对，并登记编排阶段的不可比较原因。"""
    trained = station_trained_workers(assets)
    remedies_by_station = parse_remedies(assets)

    plans: list[PairPlan] = []
    for (worker, station), station_runs in sorted(_group_runs(runs).items()):
        plan = PairPlan(
            worker=worker,
            station=station,
            first=station_runs[0],
            second=station_runs[1] if len(station_runs) > 1 else None,
            remedies=remedies_by_station.get(station, []),
        )

        # 训练前置：该工位只允许已完成本台训练的人
        allowed = trained.get(station)
        if allowed is not None and worker not in allowed:
            plan.reason_codes.add(ReasonCode.PREMISE_MISMATCH)
            plan.notes.append(f"{worker} 未完成 {station} 的本台训练")

        for run in station_runs:
            audit = audits.get(run.id)
            if audit is None:
                continue
            plan.reason_codes.update(audit.reason_codes & BLINDING_REASONS)
            if not audit.prerequisites_available:
                plan.reason_codes.add(ReasonCode.PREMISE_MISMATCH)
                plan.notes.append(
                    f"{run.id} 前置说明未满足：" + "；".join(audit.missing_prerequisites)
                )
            if audit.escalate and audit.reason_codes & BLINDING_REASONS:
                plan.notes.append(
                    f"{run.id} 存在需负责人改变展示方法或暂缓的盲化问题"
                )

        if plan.second is None:
            plan.reason_codes.add(ReasonCode.INCOMPLETE_PAIR)
            option = completion_option(plan, assets)
            if not option.feasible:
                plan.reason_codes.add(ReasonCode.NO_FEASIBLE_PAIR)
                plan.notes.append("无法补齐：" + "；".join(option.blockers))
            else:
                plan.notes.append(
                    f"可在同工位补做 {option.fixture}（第 {option.order} 件）作为对照"
                )

        if plan.structurally_complete and not plan.counterbalanced:
            plan.reason_codes.add(ReasonCode.NO_FEASIBLE_PAIR)
            plan.notes.append("两件不是不同夹具，无法构成成对比较")

        plans.append(plan)
    return plans


def completion_option(plan: PairPlan, assets: list[Asset]) -> CompletionOption:
    """判断未完成配对能否在相同工位/夹持条件下补齐对照。"""
    first = plan.first
    assert first is not None
    used = {first.fixture}
    candidate = next((f for f in COMPARED_FIXTURES if f not in used), None)
    blockers: list[str] = []
    if candidate is None:
        blockers.append("没有可作为对照的另一款夹具")
        feasible = False
    else:
        feasible = True
        if not station_swap_available(plan.station, assets):
            blockers.append(
                f"{plan.station} 调换 {candidate} 受设备台条件限制，当前班次不可用"
            )
            feasible = False
        elif not any(a.station == plan.station for a in assets):
            blockers.append(f"{plan.station} 无设备台条件记录")
            feasible = False
    return CompletionOption(
        worker=plan.worker,
        station=plan.station,
        fixture=candidate or "",
        order=first.order + 1,
        feasible=feasible,
        blockers=tuple(blockers),
    )


def station_swap_available(station: str, assets: list[Asset]) -> bool:
    """当前班次能否在该工位调换夹具。

    设备台记录是分散登记的：关于某工位的限制可能写在另一条记录里
    （如西台记录中注明“东台同类调换需要下个班”），因此按工位名跨记录
    检索含“下个班”的句子；命中则当前班次不可调换，未来班次仍可补做。
    """
    import re

    pattern = re.compile(re.escape(station) + r"[^；;。]*下个班")
    for asset in assets:
        if pattern.search(asset.limits):
            return False
    # 本工位记录明确“都可轮用”视为可用；无任何相关记录时保守视为可用，
    # 由调用方另行要求存在该工位的设备台记录。
    return True


def _fixture_available(limits: str, fixture: str) -> bool:
    """设备台记录下该夹具当前是否可轮用。

    “K2/K3 都可轮用”视为可用；“需要下个班”视为当前班次不可用，
    但不否定未来班次补做的可能。
    """
    head = limits.split("；", 1)[0]
    if "都可轮用" in head:
        return True
    if "下个班" in limits:
        return False
    return True


def counterbalance_summary(plans: list[PairPlan]) -> dict:
    """统计两款夹具在各工位、各顺序位置上的覆盖情况。"""
    cells: dict[tuple[str, str, int], int] = {}
    for plan in plans:
        for run, position in ((plan.first, 1), (plan.second, 2)):
            if run is None:
                continue
            cells[(plan.station, run.fixture, position)] = (
                cells.get((plan.station, run.fixture, position), 0) + 1
            )
    orders = [plan.fixtures for plan in plans if plan.counterbalanced]
    order_patterns = {"->".join(pair): 0 for pair in orders}
    for pair in orders:
        order_patterns["->".join(pair)] += 1
    return {
        "cells": {f"{station}|{fixture}|第{pos}次": n for (station, fixture, pos), n in cells.items()},
        "order_patterns": order_patterns,
        "balanced": len(order_patterns) >= 2,
    }


def locked_runs(runs: list[Run]) -> list[Run]:
    """已真实开始、不可重新排序的试用。"""
    return [run for run in runs if run.phase.started]
