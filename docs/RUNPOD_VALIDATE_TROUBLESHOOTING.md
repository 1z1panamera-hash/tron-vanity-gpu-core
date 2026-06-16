# RunPod Validate Troubleshooting

Date: 2026-06-17

Purpose: decide what to do if the first `validate_vectors` RunPod run fails.

Do not run benchmark while any validation issue is unresolved.

## Build Fails Before Endpoint Starts

Possible causes:

- CUDA base image tag is unavailable.
- GitHub integration cannot access the repository.
- Docker build timeout.
- Image size or registry limit.
- Dockerfile path is wrong.

Allowed fixes:

- Confirm Dockerfile path is `Dockerfile`.
- Confirm repository root contains `Dockerfile`, `app.py`, `requirements.txt`, `src/`, and `tests/phase0_test_vectors.json`.
- Change `CUDA_BASE_IMAGE` to a RunPod-compatible CUDA devel image.
- Retry GitHub integration build.

Forbidden fixes:

- Do not build on 47.80.70.211.
- Do not paste RunPod API keys into repository files.
- Do not paste Docker passwords into repository files.

## Worker Starts But `compile.ready` Is False

Inspect response fields:

- `compile.reason`
- `compile.stderr`
- `compile.stdout`

Common causes:

- `ALLOW_RUNTIME_NVCC=1` missing.
- `nvcc` missing from base image.
- CUDA source compile error.
- `-arch=native` unsupported in the worker environment.

Allowed fixes:

- Set `ALLOW_RUNTIME_NVCC=1`.
- Use a CUDA `devel` image, not `runtime`.
- If `-arch=native` fails on RunPod, change compile flags in `app.py` to a specific architecture after identifying the GPU.

Do not enable benchmark.

## `gpu_binary.returncode` Is Non-Zero

Inspect:

- `gpu_binary.stderr`
- `gpu_binary.stdout`
- `gpu_result`

Common causes:

- CUDA runtime error.
- secp256k1 device code mismatch.
- Base58/Keccak/SHA mismatch.
- Validation vector parser issue.

Allowed fixes:

- Fix CUDA correctness code locally.
- Rerun local `scripts/local_preflight.sh`.
- Redeploy and rerun `validate_vectors`.

Do not treat partial vector pass as acceptable.

## `phase0_vectors.passed` Is False

This means local public test vector file validation failed.

Allowed fixes:

- Check `tests/phase0_test_vectors.json`.
- Check required fields.
- Do not replace vectors with unreviewed output.

Do not benchmark.

## Forbidden Key Leakage Detected

If `scripts/inspect_runpod_result.py` reports any forbidden key path:

- `private_key`
- `mnemonic`
- `seed`
- `token`
- `secret`
- `api_key`

Stop immediately.

Do not run benchmark. Do not paste the full response into public channels if it contains secrets. Redact and inspect locally.

## Validation Passes But Benchmark Fails

Only applies after validation passed and benchmark was explicitly enabled.

Common causes:

- `ALLOW_GPU_BENCHMARK=1` missing.
- `max_attempts` too low to produce useful speed.
- CUDA kernel runtime error.
- Incremental walking bug.

Allowed first response:

- Keep `duration_seconds=5`.
- Keep `max_attempts=1024` for smoke.
- Inspect with `scripts/inspect_runpod_result.py`.

Do not jump to 30 or 300 seconds.

## When To Stop And Redesign

Stop and redesign if:

- Validate vectors cannot pass.
- Benchmark output is not complete TRON `addresses_per_second`.
- Output leaks forbidden key material.
- Speed is far below target even in incremental mode.

Next redesign direction:

- precomputed-window point walking,
- lower-level field arithmetic optimization,
- reviewed seed/shard policy,
- age encryption path for production matches.
