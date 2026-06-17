#!/usr/bin/env python3
import argparse
import json
import math


SEARCH_SPACE = 58 ** 6
TARGETS = {
    "p50": 0.50,
    "p90": 0.90,
    "p95": 0.95,
    "p99": 0.99,
}


def required_speed(probability: float, seconds: float) -> float:
    return -math.log(1.0 - probability) * SEARCH_SPACE / seconds


def probability_for_speed(speed: float, seconds: float) -> float:
    return 1.0 - math.exp(-(speed * seconds) / SEARCH_SPACE)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capacity math for TRON full prefix_len=2 + suffix_len=5; leading T is fixed, so random space is 58^6."
    )
    parser.add_argument("--addresses-per-second", type=float, default=0.0)
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()

    speed = max(0.0, args.addresses_per_second)
    seconds = max(0.001, args.seconds)
    required = {label: required_speed(prob, seconds) for label, prob in TARGETS.items()}
    workers = {
        label: (math.ceil(req / speed) if speed > 0 else None)
        for label, req in required.items()
    }

    print(json.dumps({
        "rule": "TRON product rule prefix_after_t=1 + suffix=5",
        "internal_rule": "Python maps product input to full Base58 prefix_len=2 + suffix_len=5 for the CUDA binary.",
        "effective_random_rule": "TRON leading T is fixed; random search is 1 character after T plus 5 suffix characters.",
        "search_space": SEARCH_SPACE,
        "seconds": seconds,
        "single_worker_addresses_per_second": speed,
        "single_worker_probability": probability_for_speed(speed, seconds) if speed > 0 else 0.0,
        "required_total_addresses_per_second": required,
        "required_workers": workers,
        "notes": [
            "Uses independent random-search probability approximation.",
            "Do not count the leading T as a random Base58 character.",
            "Inputs must be complete TRON addresses_per_second, not hash speed.",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
