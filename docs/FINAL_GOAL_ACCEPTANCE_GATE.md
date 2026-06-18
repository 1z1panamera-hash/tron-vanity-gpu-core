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
- Patched VanitySearch TRON suffix-only path passed the normal RunPod GPU Pod speed gate on NVIDIA RTX PRO 6000 Blackwell Server Edition.
- Best observed suffix-only speed: about `1.54328B complete TRON attempts/s`.
- For `58^5`, that estimates mean match time around `0.43s` and P90 around `0.98s` before Serverless overhead.
- Python wrapper has a gated `find` mode contract.
- Patched VanitySearch can emit one internal TRON JSON hit for `find`, and `app.py` age-encrypts it before returning.
- Serverless build, smoke, and cold/warm E2E timing are not complete yet.
- Find-mode safety contract is documented in `docs/AGE_ENCRYPTED_FIND_MODE.md`.

## Next Gate

Run the Serverless migration gates in order:

1. Build the RunPod Serverless image from the current GitHub repo.
2. Confirm the image builds `/app/build/vanitysearch_tron_worker` from the current patch.
3. Run one ordinary GPU Pod or Serverless smoke request with a test suffix and test age recipient.
4. Inspect the response with `scripts/inspect_runpod_result.py ... --mode find`.
5. If using a local test identity, inspect the age envelope with `scripts/verify_age_encrypted_find_response.py`.
6. Run `1 cold + 10 warm` Serverless find requests and inspect them with `scripts/inspect_serverless_find_e2e.py`.
