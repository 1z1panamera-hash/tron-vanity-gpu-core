#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TEXT_FILES = {
    ROOT / "README.md",
    ROOT / "src" / "vanity18035" / "config.py",
    ROOT / "scripts" / "check_boundary.py",
}
FORBIDDEN = (
    "/opt/vanity-address-api",
    "127.0.0.1:18030",
    "127.0.0.1:18031",
    "127.0.0.1:18032",
    "43.207.236.210:18030",
    "43.207.236.210:18031",
    "43.207.236.210:18032",
)

violations: list[str] = []
for path in ROOT.rglob("*"):
    if not path.is_file() or path in ALLOWED_TEXT_FILES or ".git" in path.parts:
        continue
    if path.suffix.lower() not in {".py", ".sh", ".service", ".toml", ".json", ".md", ".txt"}:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    for forbidden in FORBIDDEN:
        if forbidden in text:
            violations.append(f"{path.relative_to(ROOT)} contains {forbidden}")

if violations:
    raise SystemExit("\n".join(violations))
print("production boundary check passed")
