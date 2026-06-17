# Final Goal Acceptance Gate

## Objective

Find a TRON vanity address in about 10 seconds using RunPod Serverless workers, with `47.80.70.211` acting only as the controller/API server.

## Matching Rule

- Product input:
  - `prefix_after_t`: 1 custom Base58 character immediately after fixed `T`
  - `suffix`: 5 custom Base58 characters at the end of the address
- Python wrapper derives the lower-level full-address matcher:
  - internal `target_address = "T" + prefix_after_t + filler + suffix`
  - internal `prefix_len = 2`
  - internal `suffix_len = 5`
- Normal TRON addresses start with fixed `T`.
- Effective random target:
  - 1 variable prefix character after `T`
  - 5 suffix characters
- Effective search space:

```text
58^6 = 38,068,692,544
```

Do not call the product rule "front2+back5" and do not report `58^7` capacity math for this product rule.

## Completion Requirements

The goal is not complete until all of these are true:

1. RunPod Serverless worker uses a CUDA/OpenCL GPU core, not CPU correctness mode.
2. Worker validates TRON address math against public test vectors.
3. Worker accepts product input `prefix_after_t` + `suffix`.
4. Python remains a thin RunPod Serverless handler and calls a CUDA/C++ binary for computation.
5. CUDA/C++ implements private-key generation, secp256k1 point math, Keccak, Base58Check, and matching.
6. Benchmark reports complete TRON `addresses_per_second`, not hash speed or raw key stepping only.
7. Average time to match is no more than 10 seconds.
8. P90 time to match is no more than 15 seconds.
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
- VanitySearch TRON CPU adapter exists only as a local candidate patch.
- VanitySearch TRON GPU hot path is not implemented yet.
- No complete TRON `addresses_per_second` benchmark from the VanitySearch TRON path exists yet.
- Python wrapper has a gated `find` mode contract, but the CUDA/C++ `--find` implementation is not complete yet.
- Find-mode safety contract is documented in `docs/AGE_ENCRYPTED_FIND_MODE.md`.

## Next Gate

Run a low-cost x86 Linux RunPod Pod check:

1. Clone upstream VanitySearch at `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`.
2. Apply local patch `工作记录/vanitysearch_tron_cpu_prototype_20260617.patch`.
3. Run `scripts/runpod_verify_tron_cpu_vectors.sh`.
4. Continue to GPU TRON path only if it prints `tron_cpu_vectors_passed`.
