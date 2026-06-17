# Final Goal Acceptance Gate

## Objective

Find a TRON vanity address in about 10 seconds using RunPod Serverless workers, with `47.80.70.211` acting only as the controller/API server.

## Matching Rule

- Matching is performed on the full TRON Base58Check address.
- Runtime parameters:
  - `prefix_len = 2`
  - `suffix_len = 5`
- Normal TRON addresses start with fixed `T`.
- Effective random target:
  - 1 variable prefix character after `T`
  - 5 suffix characters
- Effective search space:

```text
58^6 = 38,068,692,544
```

Do not report `58^7` capacity math for this product rule.

## Completion Requirements

The goal is not complete until all of these are true:

1. RunPod Serverless worker uses a CUDA/OpenCL GPU core, not CPU correctness mode.
2. Worker validates TRON address math against public test vectors.
3. Benchmark reports complete TRON `addresses_per_second`, not hash speed or raw key stepping only.
4. A 10-second Serverless run shows enough throughput for the `58^6` target, or sharded workers demonstrate the needed aggregate throughput.
5. Output contains no plaintext `private_key`, WIF, mnemonic, seed, token, or secret.
6. Production hit flow returns only `matched_address` and `encrypted_private_key`.
7. Private key encryption uses customer `age recipient`.
8. `47.80.70.211` does not run GPU, CUDA compile, brute force, or high benchmark.
9. `47.80.70.211` only runs the controller/API and persists non-secret job metadata.
10. Existing ports `8000`, `8001`, and `18022` remain unaffected.

## Current Status

Not complete.

Current evidence:

- In-house CUDA scaffold validates TRON math but is far too slow.
- VanitySearch upstream A100 Bitcoin baseline reached billion-class key/s, proving the architecture class is promising.
- VanitySearch TRON CPU adapter exists only as a local candidate patch.
- VanitySearch TRON GPU hot path is not implemented yet.
- No complete TRON `addresses_per_second` benchmark from the VanitySearch TRON path exists yet.

## Next Gate

Run a low-cost x86 Linux RunPod Pod check:

1. Clone upstream VanitySearch at `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`.
2. Apply local patch `工作记录/vanitysearch_tron_cpu_prototype_20260617.patch`.
3. Run `scripts/runpod_verify_tron_cpu_vectors.sh`.
4. Continue to GPU TRON path only if it prints `tron_cpu_vectors_passed`.
