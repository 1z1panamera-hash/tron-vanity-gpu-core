# GitHub Ready Manifest

Date: 2026-06-17

Purpose: define the exact local directory that can be pushed to GitHub for RunPod GitHub integration.

## Repository Root

Use this directory as the GitHub repository root:

```text
gpu-core/
```

Do not use 47.80.70.211 as the GitHub source, build machine, CUDA compiler, Docker builder, or benchmark runner.

## Required Files

- `README.md`
- `.gitignore`
- `.dockerignore`
- `Dockerfile`
- `Dockerfile.cuda-validate`
- `app.py`
- `requirements.txt`
- `RUNPOD_VALIDATE_PAYLOAD.json`
- `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`
- `RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json`
- `RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json`
- `src/GPU_CORE_CONTRACT.json`
- `src/tron_gpu_core.cu`
- `src/tron_core_device.cuh`
- `src/secp256k1_device.cuh`
- `tests/phase0_test_vectors.json`
- `tests/verify_phase0_vectors.py`
- `tests/verify_incremental_walking.cpp`
- `tests/verify_batch_inversion.cpp`
- `tests/verify_batch_point_add.cpp`
- `tests/verify_shard_schedule.cpp`
- `scripts/local_preflight.sh`
- `scripts/public_repo_audit.py`
- `scripts/prepare_github_push.sh`
- `scripts/inspect_runpod_result.py`
- `scripts/inspect_vanitysearch_benchmark.py`
- `scripts/capacity_math.py`
- `examples/runpod_validate_success_sample.json`
- `examples/runpod_benchmark_success_sample.json`
- `examples/vanitysearch_bounded_benchmark_sample.txt`
- `docs/RUNPOD_GITHUB_DEPLOY_PATH.md`
- `docs/RUNPOD_GITHUB_UPLOAD_CHECKLIST.md`
- `docs/RUNPOD_ACTION_NOW.md`
- `docs/RUNPOD_DEPLOYMENT_ROUTE_DECISION_20260617.md`
- `docs/RUNPOD_FLASH_FALLBACK_PROBE.md`
- `docs/RUNPOD_RESPONSE_INTAKE.md`
- `docs/RUNPOD_RESULT_INSPECTION.md`
- `docs/RUNPOD_CONSOLE_CHECKLIST.md`
- `docs/RUNPOD_VALIDATE_TROUBLESHOOTING.md`
- `docs/RUNPOD_FIRST_TEST_SEQUENCE.md`
- `docs/RUNPOD_BENCHMARK_GATE.md`
- `docs/RUNPOD_A100_RTX5090_COMPARISON.md`
- `docs/SERVER_PREFLIGHT_47.md`

## Excluded From Git And Docker Context

The repository must not include:

- `.env`
- RunPod API key
- Docker registry password
- private key
- token
- secret
- `.pem`
- `.key`
- build output
- benchmark logs

The Docker image intentionally copies only:

- `requirements.txt`
- `app.py`
- `src/`
- `tests/phase0_test_vectors.json`

Docs and local validation reports are not copied into the worker image.

## Local Preflight

Before pushing to GitHub, run:

```bash
scripts/local_preflight.sh
```

Expected final line:

```text
local_preflight_passed
```

This preflight does not connect to 47.80.70.211, does not call RunPod, does not build Docker, and does not run a real benchmark.

Latest local preflight result:

```text
local_preflight_passed
```

## Local Upload Archive

Generated archive:

```text
../tron-vanity-gpu-core-github-ready-20260617.tar.gz
```

The archive excludes generated validation reports, Python caches, build outputs, and secret-like filenames.

The archive SHA-256 is recorded outside this repository in the local server `说明.md` after packaging.
Do not store the archive hash inside this repository because the archive includes this manifest and would become self-referential.

## RunPod First Deployment

In RunPod GitHub integration:

- Repository root: this `gpu-core` directory.
- Dockerfile path: `Dockerfile`.
- Endpoint type: `Queue`.
- First environment:

```text
ALLOW_RUNTIME_NVCC=1
```

Do not set:

```text
ALLOW_GPU_BENCHMARK=1
```

## First Request

Use `RUNPOD_VALIDATE_PAYLOAD.json`:

```json
{
  "input": {
    "mode": "validate_vectors"
  },
  "policy": {
    "executionTimeout": 300000,
    "ttl": 900000
  }
}
```

## Pass Gate

Only proceed to benchmark if RunPod returns:

- `mode = validate_vectors`
- `phase0_vectors.passed = true`
- `compile.ready = true`
- `gpu_binary.returncode = 0`
- `passed = true`

If validation fails, do not run benchmark. Inspect RunPod build logs and worker logs first.

## Benchmark Gate

Benchmark is allowed only after validation passes and only after explicitly setting:

```text
ALLOW_GPU_BENCHMARK=1
```

First benchmark must use `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`.

Only after smoke passes, compare A100 and RTX 5090-class endpoints with:

- `RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json`
- `RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json`

The benchmark output must not contain:

- `private_key`
- `mnemonic`
- `seed`
- `token`
- `secret`
