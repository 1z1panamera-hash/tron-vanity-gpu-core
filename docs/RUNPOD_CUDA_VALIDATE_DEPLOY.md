# RunPod CUDA Validate Deploy

Date: 2026-06-17

Purpose: run only Phase 0 vector validation on RunPod CUDA hardware.

This is not a benchmark and must not be used to claim RTX 5090/A100 speed.

Preferred deployment path: `docs/RUNPOD_GITHUB_DEPLOY_PATH.md`.

Use manual Docker build/push only if a separate approved build machine or registry pipeline is available. Do not use 47.80.70.211 for Docker build, CUDA compile, or benchmark work.

## Current Worker Shape

- `Dockerfile` and `Dockerfile.cuda-validate` use a CUDA devel image with `nvcc`.
- `ALLOW_RUNTIME_NVCC=1` lets `app.py` compile `src/tron_gpu_core.cu` inside the RunPod worker.
- Runtime compile uses `nvcc -std=c++17 -O2 -arch=native`.
- Handler mode: `validate_vectors`.

## Build Backup Path

Example image name:

```bash
docker build \
  -f Dockerfile \
  -t YOUR_REGISTRY/tron-vanity-gpu-core:cuda-validate-v1 .
```

`Dockerfile.cuda-validate` is kept as a named backup for validate-only deployments.

If the CUDA base image tag is not available or does not support the selected GPU, update:

```bash
--build-arg CUDA_BASE_IMAGE=nvidia/cuda:<confirmed-devel-tag>
```

For RTX 5090/Blackwell, use a CUDA image new enough for that GPU. For A100, an Ampere-capable CUDA devel image is sufficient, but keeping one recent image is simpler.

## Push Backup Path

```bash
docker push YOUR_REGISTRY/tron-vanity-gpu-core:cuda-validate-v1
```

Do not write Docker registry passwords or RunPod API keys into files.

## RunPod Endpoint

Create a RunPod Serverless endpoint using either the pushed image or the GitHub integration build.

First test payload:

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

Use `/run` or the RunPod console request tab. `/runsync` is acceptable only if the endpoint returns within the synchronous timeout, but `/run` is safer for cold-start plus runtime compile.

## Pass Criteria

The response must show:

- `mode = validate_vectors`
- `phase0_vectors.passed = true`
- `compile.ready = true`
- `gpu_binary.returncode = 0`
- `passed = true`

The response must not contain plaintext key material or credential material.

## After Pass

Only after this passes on RunPod:

1. enable `ALLOW_GPU_BENCHMARK=1` only on the approved endpoint,
2. run `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`,
3. confirm the output reports complete `addresses_per_second`,
4. test A100,
5. test RTX 5090,
6. calculate worker count for the 10 second prefix2+suffix5 goal.

The benchmark smoke path exists, but it is not yet a final optimized GPU generator.
