# Final Goal Acceptance Gate

## Objective

Find a TRON vanity address with a 5-character suffix using RunPod Serverless workers, with `47.80.70.211` acting only as the controller/API server.

## Matching Rule

- Product input:
  - `suffix`: 5 custom Base58 characters at the end of the address
- Python wrapper derives the lower-level full-address matcher:
  - internal `target_address = "T" + filler + suffix`
  - internal `prefix_len = 0`
  - internal `suffix_len = 5`
- Normal TRON addresses start with fixed `T`.
- No prefix-after-`T` character is matched.
- The last 5 Base58Check address characters are matched, so checksum logic must be correct.
- Effective random target: 5 suffix characters
- Effective search space:

```text
58^5 = 656,356,768
```

Do not call the product rule "front2+back5" and do not report `58^6` or `58^7` capacity math for this product rule.

## Completion Requirements

The goal is not complete until all of these are true:

1. RunPod Serverless worker uses a CUDA/OpenCL GPU core, not CPU correctness mode.
2. Worker validates TRON address math against public test vectors.
3. Worker accepts product input `suffix`.
4. Python remains a thin RunPod Serverless handler and calls a CUDA/C++ binary for computation.
5. CUDA/C++ implements private-key generation, secp256k1 point math, Keccak, Base58Check, and matching.
6. Benchmark reports complete TRON `addresses_per_second`, not hash speed or raw key stepping only.
7. Average time to match is no more than 5 seconds.
8. P90 time to match is no more than 8 seconds.
9. Output contains no plaintext `private_key`, WIF, mnemonic, seed, token, or secret.
10. Production hit flow returns only `matched_address` and `encrypted_private_key`.
11. Private key encryption uses customer `age recipient`.
12. `47.80.70.211` does not run GPU, CUDA compile, brute force, or high benchmark.
13. `47.80.70.211` only runs the controller/API and persists non-secret job metadata.
14. Existing ports `8000`, `8001`, and `18022` remain unaffected.

## Current Status

Not complete.

Current evidence:

- In-house CUDA scaffold validates TRON math but is far too slow.
- VanitySearch upstream A100 Bitcoin baseline reached billion-class key/s, proving the architecture class is promising.
- VanitySearch TRON GPU path has passed a prior prefix+suffix bounded GPU Pod test, but that result is historical and not the suffix-only target.
- Suffix-only hot path and benchmark gate still need to be updated and retested on RunPod GPU Pod.
- Python wrapper has a gated `find` mode contract.
- CUDA/C++ `--find` now has a staging implementation for wrapper integration, but it is not yet RunPod-compiled or performance-validated.
- The current `--find` implementation uses the deterministic staging candidate schedule, not the final high-performance/randomized production core.
- Find-mode safety contract is documented in `docs/AGE_ENCRYPTED_FIND_MODE.md`.

## Next Gate

Run a low-cost x86 Linux RunPod Pod check:

1. Clone upstream VanitySearch at `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`.
2. Apply local patch `工作记录/vanitysearch_tron_cpu_prototype_20260617.patch`.
3. Run `scripts/runpod_verify_tron_cpu_vectors.sh`.
4. Continue to GPU TRON path only if it prints `tron_cpu_vectors_passed`.
