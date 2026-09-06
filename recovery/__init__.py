"""Source-layout bootstrap for local ``python -m recovery`` execution."""

import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC_ROOT))
__path__.append(str(_SRC_ROOT / "recovery"))
