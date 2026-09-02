"""Source-layout bootstrap for local ``python -m recovery`` execution."""

from pathlib import Path

__path__.append(str(Path(__file__).resolve().parent.parent / "src" / "recovery"))
