#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / "SPEC_LOCK.json").read_text(encoding="utf-8"))
spec = (ROOT / lock["spec_path"]).resolve()
superseded = (ROOT / lock["superseded_spec"]).resolve()

actual = hashlib.sha256(spec.read_bytes()).hexdigest()
if actual != lock["sha256"]:
    raise SystemExit(f"authoritative spec SHA mismatch: expected={lock['sha256']} actual={actual}")

old_header = superseded.read_text(encoding="utf-8").splitlines()[:4]
if not any("已停止使用" in line for line in old_header):
    raise SystemExit("superseded V2 specification is not clearly marked as stopped")

print(f"authoritative spec verified: {spec.name} sha256={actual}")
