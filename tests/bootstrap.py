"""测试引导：在隔离模式（python -I）下把项目根目录加入 sys.path。

业务资料目录始终不加入 sys.path，避免资料内植入模块被导入。
所有测试模块在导入项目包之前先 `from tests import bootstrap` 即可。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
