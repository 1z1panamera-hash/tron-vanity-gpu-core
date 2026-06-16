import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
VECTOR_PATH = ROOT / "tests" / "phase0_test_vectors.json"
REPORT_PATH = ROOT / "tests" / "phase0_filter_validation_report.json"
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_INDEX = {char: index for index, char in enumerate(BASE58_ALPHABET)}


def base58_decode(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in BASE58_INDEX:
            raise ValueError(f"invalid Base58 char: {char}")
        number = number * 58 + BASE58_INDEX[char]

    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading_zeroes + raw


def check_vectors() -> Dict[str, object]:
    data = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    vectors: List[Dict[str, str]] = data["vectors"]
    failures = []
    required = {
        "label",
        "private_key_hex",
        "public_key_uncompressed_hex",
        "keccak256_pubkey_without_04",
        "tron_hex_address",
        "payload25_hex",
        "tron_base58_address",
        "prefix2",
        "suffix5",
        "source",
        "warning",
    }

    for vector in vectors:
        label = vector.get("label", "<missing>")
        missing = sorted(required - set(vector))
        if missing:
            failures.append({"label": label, "missing": missing})
            continue

        if vector["source"] != "TEST_ONLY_PUBLIC_VECTOR":
            failures.append({"label": label, "source": vector["source"]})
        if vector["warning"] != "TEST_ONLY_PUBLIC_VECTOR_DO_NOT_USE_FOR_FUNDS":
            failures.append({"label": label, "warning": vector["warning"]})

        decoded = base58_decode(vector["tron_base58_address"])
        if decoded.hex() != vector["payload25_hex"]:
            failures.append({"label": label, "base58_payload": "mismatch"})

        address = vector["tron_base58_address"]
        if vector["prefix2"] != address[:2]:
            failures.append({"label": label, "prefix2": "mismatch"})
        if vector["suffix5"] != address[-5:]:
            failures.append({"label": label, "suffix5": "mismatch"})

    return {
        "vector_path": str(VECTOR_PATH),
        "report_path": str(REPORT_PATH),
        "total_vectors": len(vectors),
        "passed": len(failures) == 0,
        "failures": failures,
        "notes": [
            "These are public TEST_ONLY vectors.",
            "Do not use test private keys for funds.",
            "This script does not generate random private keys and does not benchmark.",
        ],
    }


def main() -> None:
    print(json.dumps(check_vectors(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
