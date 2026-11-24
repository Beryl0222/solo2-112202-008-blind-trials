"""兼容资料包根目录下的 pack_check 模块与默认资料路径。

项目脚本与业务资料分目录存放；本模块负责把资料包根目录加入导入路径，
使隔离模式（python -I）下也能复用既有格式校验。
"""
from __future__ import annotations

import sys
from pathlib import Path

_PACK_ROOT = Path(__file__).resolve().parent.parent
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from pack_check import DEFAULT_DATA  # noqa: E402  (路径注入后导入)


def data_directory(directory: Path | None) -> Path:
    """返回资料目录；未显式给出时使用资料包默认目录。"""
    if directory is None:
        return DEFAULT_DATA
    return directory
