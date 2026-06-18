#!/usr/bin/env python3
"""Generate a local test-only age X25519 identity without external tools."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Iterable, List


P = 2 ** 255 - 19
A24 = 121665
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def x25519(k: bytes, u: bytes) -> bytes:
    if len(k) != 32 or len(u) != 32:
        raise ValueError("X25519 inputs must be 32 bytes")
    scalar = bytearray(k)
    scalar[0] &= 248
    scalar[31] &= 127
    scalar[31] |= 64
    n = int.from_bytes(scalar, "little")
    x1 = int.from_bytes(u, "little") % P
    x2, z2 = 1, 0
    x3, z3 = x1, 1
    swap = 0
    for t in range(254, -1, -1):
        k_t = (n >> t) & 1
        swap ^= k_t
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = k_t
        a = (x2 + z2) % P
        aa = (a * a) % P
        b = (x2 - z2) % P
        bb = (b * b) % P
        e = (aa - bb) % P
        c = (x3 + z3) % P
        d = (x3 - z3) % P
        da = (d * a) % P
        cb = (c * b) % P
        x3 = ((da + cb) ** 2) % P
        z3 = (x1 * ((da - cb) ** 2)) % P
        x2 = (aa * bb) % P
        z2 = (e * (aa + A24 * e)) % P
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    out = (x2 * pow(z2, P - 2, P)) % P
    return out.to_bytes(32, "little")


def bech32_polymod(values: Iterable[int]) -> int:
    generators = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ value
        for i, generator in enumerate(generators):
            if (top >> i) & 1:
                chk ^= generator
    return chk


def bech32_hrp_expand(hrp: str) -> List[int]:
    return [ord(ch) >> 5 for ch in hrp] + [0] + [ord(ch) & 31 for ch in hrp]


def convertbits(data: bytes, from_bits: int, to_bits: int, pad: bool = True) -> List[int]:
    acc = 0
    bits = 0
    ret: List[int] = []
    maxv = (1 << to_bits) - 1
    max_acc = (1 << (from_bits + to_bits - 1)) - 1
    for value in data:
        if value < 0 or value >> from_bits:
            raise ValueError("invalid value for convertbits")
        acc = ((acc << from_bits) | value) & max_acc
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (to_bits - bits)) & maxv)
    elif bits >= from_bits or ((acc << (to_bits - bits)) & maxv):
        raise ValueError("invalid incomplete group")
    return ret


def bech32_encode(hrp: str, payload: bytes, uppercase: bool = False) -> str:
    data = convertbits(payload, 8, 5, True)
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    encoded = hrp + "1" + "".join(BECH32_CHARSET[value] for value in data + checksum)
    return encoded.upper() if uppercase else encoded


def generate_identity() -> tuple[str, str]:
    private_key = os.urandom(32)
    public_key = x25519(private_key, bytes([9]) + bytes(31))
    identity = bech32_encode("age-secret-key-", private_key, uppercase=True)
    recipient = bech32_encode("age", public_key)
    return identity, recipient


def self_test() -> None:
    scalar = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    u = bytes([9]) + bytes(31)
    expected = "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    actual = x25519(scalar, u).hex()
    if actual != expected:
        raise RuntimeError(f"X25519 self-test failed: {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local test-only age identity file.")
    parser.add_argument("--identity", default="/tmp/tron_vanity_test_age_identity.txt")
    parser.add_argument("--force", action="store_true", help="overwrite an existing identity file")
    args = parser.parse_args()

    self_test()
    identity_path = Path(args.identity)
    if not str(identity_path).startswith("/tmp/"):
        raise SystemExit("identity path must be under /tmp")
    if identity_path.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite existing identity file: {identity_path}")
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity, recipient = generate_identity()
    identity_path.write_text(identity + "\n", encoding="utf-8")
    os.chmod(identity_path, stat.S_IRUSR | stat.S_IWUSR)
    print(json.dumps({
        "mode": "generate_test_age_identity",
        "passed": True,
        "recipient": recipient,
        "identity_path": str(identity_path),
        "notes": [
            "This is test-only material for RunPod smoke/E2E validation.",
            "The identity value is written to the identity_path and is not printed.",
            "Delete the identity file after smoke/E2E inspection.",
        ],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
