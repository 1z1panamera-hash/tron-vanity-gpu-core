# Build And RunPod Gate

Current status: build is not authorized in this step.

Preferred build/deploy path is RunPod GitHub integration, documented in `docs/RUNPOD_GITHUB_DEPLOY_PATH.md`, because local Docker is unavailable and 47.80.70.211 is not allowed to build images.

## Allowed Later Only After Confirmation

- Build Docker image.
- Push image to a registry.
- Create or update RunPod Serverless endpoint.
- Call RunPod API.
- Run GPU benchmark.

## First Build Target

The first image should be a correctness image, not a speed claim.

Required first test:

```json
{
  "input": {
    "mode": "validate_vectors"
  }
}
```

This must pass before any `benchmark` payload.

Current `src/tron_gpu_core.cu` has a CUDA `validate_vectors_kernel`, but it still requires an environment with `nvcc` and a CUDA-capable worker to compile and run it.

Do not set `ALLOW_GPU_BENCHMARK=1` during the first GitHub integration deployment. First endpoint run must be validation only.

## First Benchmark Target

After vector validation passes, first benchmark must be short:

```json
{
  "input": {
    "mode": "benchmark",
    "target_address": "TX8888888888888888888888888886666",
    "prefix_len": 2,
    "suffix_len": 5,
    "duration_seconds": 5,
    "max_attempts": 1024,
    "start_counter": 0,
    "shard_id": 0,
    "shard_count": 1
  }
}
```

Do not start with 30 or 300 seconds.
Do not enable benchmark unless `ALLOW_GPU_BENCHMARK=1` is explicitly set on the approved RunPod endpoint.
Use `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json` for the first request.

## Pass Criteria

The build can move to GPU speed comparison only if:

- `validate_vectors` passes.
- Benchmark output has `addresses_per_second`.
- Benchmark output clearly states complete TRON address generation speed.
- Benchmark output does not contain plaintext `private_key`.
- Benchmark output does not contain token, secret, seed, or mnemonic.

## Current Limitation

The current benchmark path is a smoke test for the complete TRON address chain.
It is not yet an optimized CUDA vanity generator and must not be used as the final 10 second capacity number.
