"""命令行入口：可反复编排与核定后续试装。

用法（建议以隔离模式运行，避免资料目录中的植入模块被导入）：

    python3 -I -m trialkit glossary --directory materials
    python3 -I -m trialkit audit --directory materials
    python3 -I -m trialkit plan --directory materials
    python3 -I -m trialkit adjudicate --directory materials
    python3 -I -m trialkit all --directory materials --json out.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import blinding, orchestration, reporting, terminology
from .adjudication import adjudicate
from .loading import load
from .pack_compat import data_directory


def _load(directory: Path) -> dict:
    return load(data_directory(directory))


def cmd_glossary(args) -> dict:
    data = _load(args.directory)
    glossary = terminology.build_glossary(data["instructions"])
    text = reporting.render_glossary(glossary)
    return {"text": text, "json": reporting.to_plain(glossary)}


def cmd_audit(args) -> dict:
    data = _load(args.directory)
    audits = blinding.audit_all(
        data["runs"], data["instructions"], data["assets"]
    )
    text = reporting.render_audits(audits)
    return {"text": text, "json": {"audits": reporting.to_plain(audits)}}


def cmd_plan(args) -> dict:
    data = _load(args.directory)
    audits = blinding.audit_all(
        data["runs"], data["instructions"], data["assets"]
    )
    plans = orchestration.build_pairs(data["runs"], audits, data["assets"])
    text = reporting.render_plans(plans, data["runs"])
    return {
        "text": text,
        "json": {
            "plans": reporting.to_plain(plans),
            "balance": orchestration.counterbalance_summary(plans),
            "locked_runs": [run.id for run in orchestration.locked_runs(data["runs"])],
        },
    }


def cmd_adjudicate(args) -> dict:
    data = _load(args.directory)
    audits = blinding.audit_all(
        data["runs"], data["instructions"], data["assets"]
    )
    plans = orchestration.build_pairs(data["runs"], audits, data["assets"])
    report = adjudicate(
        data["runs"],
        data["instructions"],
        data["feedback"],
        data["assets"],
        plans,
    )
    text = reporting.render_report(report)
    return {"text": text, "json": reporting.to_plain(report)}


def cmd_all(args) -> dict:
    data = _load(args.directory)
    glossary = terminology.build_glossary(data["instructions"])
    audits = blinding.audit_all(
        data["runs"], data["instructions"], data["assets"]
    )
    plans = orchestration.build_pairs(data["runs"], audits, data["assets"])
    report = adjudicate(
        data["runs"],
        data["instructions"],
        data["feedback"],
        data["assets"],
        plans,
    )
    text = "\n\n".join(
        [
            reporting.render_glossary(glossary),
            reporting.render_audits(audits),
            reporting.render_plans(plans, data["runs"]),
            reporting.render_report(report),
        ]
    )
    payload = {
        "glossary": reporting.to_plain(glossary),
        "audits": reporting.to_plain(audits),
        "plans": reporting.to_plain(plans),
        "balance": orchestration.counterbalance_summary(plans),
        "adjudication": reporting.to_plain(report),
    }
    return {"text": text, "json": payload}


COMMANDS = {
    "glossary": cmd_glossary,
    "audit": cmd_audit,
    "plan": cmd_plan,
    "adjudicate": cmd_adjudicate,
    "all": cmd_all,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--directory", type=Path, default=None, help="资料包目录")
    parser.add_argument("--json", type=Path, default=None, help="同时写出机读 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = COMMANDS[args.command](args)
    print(result["text"])
    if args.json:
        args.json.write_text(
            json.dumps(result["json"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n机读结果已写入 {args.json}")
    return 0
