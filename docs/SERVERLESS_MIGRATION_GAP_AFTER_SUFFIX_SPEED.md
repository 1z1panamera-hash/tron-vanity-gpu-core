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

## What Is Not Finished

Production `find` is intentionally not enabled for the VanitySearch backend yet.

Missing pieces:

1. A dedicated patched VanitySearch production hit mode that emits structured JSON to the Python wrapper.
2. The JSON must include:
   - `matched=true`
   - `matched_address`
   - internal-only `private_key_hex`
   - `attempts`
   - `gpu_name` if available
3. The JSON must not be returned directly to the API.
4. `app.py` must age-encrypt `private_key_hex` with customer `age_recipient`.
5. API response must include only:
   - `matched`
   - `matched_address`
   - `encrypted_private_key`
   - non-sensitive metadata
6. Serverless image must be built and tested.
7. Repeated Serverless runs must prove:
   - warm-start average <= 5s
   - warm-start P90 <= 8s
   - cold-start behavior is measured separately

## Current Safe Behavior

If `GPU_WORKER_BACKEND=vanitysearch` or `/app/build/vanitysearch_tron_worker` exists:

- `benchmark` can use the high-speed VanitySearch backend.
- `find` refuses with an explicit error until JSON hit output and age encryption are wired end-to-end.

This prevents accidentally returning plaintext key material from the upstream VanitySearch output path.

## Next Engineering Step

Patch VanitySearch with a dedicated TRON production find mode for suffix-only search:

- strict input pattern: `T*<suffix5>`
- no normal `Priv (WIF)` / `Priv (HEX)` output
- emit one compact JSON object on hit
- allow bounded `duration_seconds` / `max_attempts`
- keep benchmark mode separate from production find mode

After that, run a GPU Pod find smoke test with a deliberately easy suffix, using only a test age recipient and no customer data.
