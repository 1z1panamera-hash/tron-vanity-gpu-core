# Serverless Migration Gap After Suffix Speed Pass

Date: 2026-06-18 Asia/Shanghai

## Current Evidence

The suffix-only GPU Pod speed gate has passed.

- Result doc: `docs/RUNPOD_SUFFIX_ONLY_SPEED_SWEEP_RESULT_20260618_RTX_PRO_6000.md`
- GPU: NVIDIA RTX PRO 6000 Blackwell Server Edition
- Best speed: about `1.54328B attempts/s`
- Rule: full TRON Base58Check address last 5 characters only
- Search space: `58^5`
- Estimated mean: about `0.43s`
- Estimated P90: about `0.98s`

This proves the patched VanitySearch CUDA path is fast enough on a normal GPU Pod for the current suffix-only target.

## What Is Now Wired

- Dockerfile installs Python, age, git, compiler tools, and CUDA build prerequisites.
- Dockerfile copies the suffix-only VanitySearch patch and build helper.
- Dockerfile builds `/app/build/vanitysearch_tron_worker` during image build.
- `app.py` detects that binary and routes benchmark mode through the patched VanitySearch backend.
- Benchmark mode sets `TRON_SUPPRESS_SECRET_OUTPUT=1`.
- Benchmark mode returns only speed metadata, not raw VanitySearch output.
- Patched VanitySearch has a TRON JSON hit output mode for production `find`.
- `app.py` can call the patched VanitySearch backend for `find`, parse the internal JSON hit, and age-encrypt the internal key value before returning.
- Local contract tests cover both the original self-written worker path and the patched VanitySearch worker path.

## What Is Not Finished

Production `find` is wired locally, but it is not RunPod-proven yet.

Missing pieces:

1. Serverless image must be built with the updated patch.
2. A normal GPU Pod find smoke test should prove the patched binary emits exactly one internal JSON hit for an easy test suffix.
3. Serverless calls must prove the Python wrapper returns only:
   - `matched`
   - `matched_address`
   - `encrypted_private_key`
   - non-sensitive metadata
4. Repeated Serverless runs must prove:
   - warm-start average <= 5s
   - warm-start P90 <= 8s
   - cold-start behavior is measured separately

## Current Safe Behavior

If `GPU_WORKER_BACKEND=vanitysearch` or `/app/build/vanitysearch_tron_worker` exists:

- `benchmark` can use the high-speed VanitySearch backend.
- `find` uses `TRON_JSON_HIT_OUTPUT=1`, parses the internal JSON hit, and returns age ciphertext plus non-sensitive metadata.
- Raw VanitySearch stdout is not returned to the API.

This prevents accidentally returning raw key material from the upstream VanitySearch output path.

## Next Engineering Step

Run a short GPU Pod build/find smoke before Serverless:

- strict input pattern: `T*<suffix5>`
- no normal `Priv (WIF)` / `Priv (HEX)` output
- emit one compact JSON object on hit internally
- prove API response contains age ciphertext only
- keep benchmark mode separate from production find mode

After that, create/update the Serverless endpoint and run cold-start plus warm-start end-to-end tests with only test recipients and no customer data.
