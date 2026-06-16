# RunPod GitHub Deploy Path

Date: 2026-06-17

Purpose: deploy the CUDA validation worker without local Docker and without using 47.80.70.211 as a build machine.

## Decision

Use RunPod's GitHub integration as the preferred deployment path.

Reason:

- The local Mac has no usable Docker.
- 47.80.70.211 must not build Docker images, compile CUDA, or run benchmark workloads.
- RunPod documentation says its GitHub integration can pull code and Dockerfile from GitHub, build the container image, store it in RunPod's registry, and deploy it to an endpoint.

Docker Hub / manual registry build remains a backup path only if a separate approved build machine is available.

## Required Repository Shape

The GitHub repository root should be this `gpu-core` directory or contain this directory as the worker root.

Required files:

- `app.py`
- `requirements.txt`
- `Dockerfile`
- `Dockerfile.cuda-validate`
- `src/`
- `tests/phase0_test_vectors.json`
- `RUNPOD_VALIDATE_PAYLOAD.json`
- `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`
- `docs/`

Do not add `.env`, RunPod API keys, Docker passwords, private keys, tokens, or secrets.

## RunPod GitHub Settings

In the RunPod console:

1. Connect GitHub in RunPod settings.
2. Create a new Serverless endpoint.
3. Select the GitHub repository and branch.
4. Set Dockerfile path to:

```text
Dockerfile
```

Backup Dockerfile path, if a separate validate-only name is preferred:

```text
Dockerfile.cuda-validate
```

5. Endpoint type:

```text
Queue
```

6. First endpoint environment:

```text
ALLOW_RUNTIME_NVCC=1
```

Do not set `ALLOW_GPU_BENCHMARK=1` for the first endpoint build.

## Why Runtime Compile Is Used

The Docker image build may not have GPU access. The current image therefore does not compile CUDA during Docker build.

Instead, `app.py` compiles `src/tron_gpu_core.cu` at runtime only when:

```text
ALLOW_RUNTIME_NVCC=1
```

This keeps the GitHub build path compatible with build environments that do not expose GPU hardware.

## First Request Only

Use only validation first:

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

Pass criteria:

- `mode = validate_vectors`
- `phase0_vectors.passed = true`
- `compile.ready = true`
- `gpu_binary.returncode = 0`
- `passed = true`

If this fails, do not run benchmark.

## Benchmark Gate

Only after validation passes:

1. enable `ALLOW_GPU_BENCHMARK=1` on the approved RunPod endpoint,
2. use `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`,
3. keep `duration_seconds = 5`,
4. keep `max_attempts = 1024` for the first smoke test,
5. inspect output for absence of `private_key`, `mnemonic`, `seed`, `token`, and `secret`.

Do not claim RTX 5090/A100 speed until benchmark output reports complete TRON `addresses_per_second`.

## Known RunPod Build Limits To Watch

If using GitHub integration, watch build logs for:

- Docker build timeout.
- Image size limits.
- CUDA base image availability.
- Any build step accidentally trying to use GPU hardware.

If GitHub integration fails because of build limits, stop and decide on a separate approved build machine. Do not move the build to 47.80.70.211.
