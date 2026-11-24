"""把通过格式校验的资料行装载为领域对象。"""
from __future__ import annotations

from pathlib import Path

from .model import Asset, Feedback, Instruction, Phase, Run
from .pack_compat import DEFAULT_DATA
from pack_check import read_tables


def _split_refs(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split("|") if part)


def load(directory: Path = DEFAULT_DATA) -> dict:
    """读取资料包并返回领域对象列表。

    只读取输入，不做任何写入，也不控制任何设备。
    """
    rows = read_tables(directory)

    instructions = [
        Instruction(
            id=row["id"],
            visible=row["visible"],
            ref=_split_refs(row["ref"]),
            text=row["text"],
        )
        for row in rows["instructions.tsv"]
    ]
    runs = [
        Run(
            id=row["id"],
            worker=row["worker"],
            order=int(row["order"]),
            station=row["station"],
            fixture=row["fixture"],
            seen=_split_refs(row["seen"]),
            phase=Phase(row["phase"]),
        )
        for row in rows["runs.tsv"]
    ]
    feedback = [
        Feedback(
            id=row["id"],
            run=row["run"],
            at=row["at"],
            author=row["author"],
            text=row["text"],
        )
        for row in rows["feedback.tsv"]
    ]
    assets = [
        Asset(id=row["id"], station=row["station"], limits=row["limits"])
        for row in rows["assets.tsv"]
    ]

    return {
        "instructions": instructions,
        "runs": runs,
        "feedback": feedback,
        "assets": assets,
    }
