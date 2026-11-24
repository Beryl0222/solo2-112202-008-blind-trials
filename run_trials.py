#!/usr/bin/env python3
"""试用编排与核定的入口脚本。

刻意兼容隔离模式：`python3 -I` 不会自动把脚本目录加入 sys.path，
这里在导入项目包之前手动注入脚本所在目录。业务资料目录始终不进入
sys.path，避免资料内植入模块（如 json.py）被解释器加载。

示例：
    python3 -I run_trials.py all
    python3 -I run_trials.py adjudicate --directory materials --json result.json
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from trialkit.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
