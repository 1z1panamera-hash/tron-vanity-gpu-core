# RunPod A100 And RTX 5090 Comparison

Purpose: measure complete TRON address generation speed on RunPod Serverless without using 47.80.70.211 for build, compile, CUDA, or benchmark work.

This is not production private key delivery. Benchmark mode must not output plaintext private keys, mnemonic, seed, token, or secret values.

## GPU Targets

- A100: CUDA compute capability 8.0.
- RTX 5090 class: CUDA compute capability 12.0.

Reference: NVIDIA CUDA GPU Compute Capability table: https://developer.nvidia.com/cuda/gpus

If RunPod labels a GPU as "5090 Ti" or similar, record the exact RunPod GPU name from `benchmark_result.gpu_name`. NVIDIA's public table lists GeForce RTX 5090 under compute capability 12.0.

## Runtime Compile Settings

The worker compiles `src/tron_gpu_core.cu` at runtime only when:

```text
ALLOW_RUNTIME_NVCC=1
```

Optional explicit architecture:

```text
CUDA_ARCH=sm_80
```

for A100, or:

```text
CUDA_ARCH=sm_120
```

for RTX 5090 class GPUs.

If `CUDA_ARCH` is not set, `app.py` tries:

```text
native, sm_120, sm_80
```

in that order. This fallback exists only to survive RunPod image/GPU differences. Do not use a successful compile as proof of speed; vector validation must pass first.

## Gate 1: Validate

Run `RUNPOD_VALIDATE_PAYLOAD.json` first on each endpoint or GPU class.

Required pass fields:

- `mode = validate_vectors`
- `phase0_vectors.passed = true`
- `compile.ready = true`
- `gpu_binary.returncode = 0`
- `passed = true`

If this fails, stop. Do not benchmark.

## Gate 2: Smoke

After validation passes, set:

```text
ALLOW_GPU_BENCHMARK=1
```

Run `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`.

This uses `duration_seconds=5` and `max_attempts=1024`. It is only a handler/kernel smoke test and cannot represent real GPU speed.

## Gate 3: 10 Second Comparison

Only after smoke passes:

- On an A100 endpoint, run `RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json`.
- On an RTX 5090-class endpoint, run `RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json`.

Both payloads use:

- `kernel_mode=incremental`
- `duration_seconds=10`
- `max_attempts=10000000000`

Compare only:

- `benchmark_result.gpu_name`
- `benchmark_result.kernel_mode`
- `benchmark_result.attempts`
- `benchmark_result.elapsed_seconds`
- `benchmark_result.addresses_per_second`
- `benchmark_result.keys_per_second`

Do not compare hash speed. This benchmark must count complete TRON address attempts.

## Result Inspection

Save each RunPod response JSON locally and inspect it:

```bash
scripts/inspect_runpod_result.py runpod_a100_10s_response.json --mode benchmark
scripts/inspect_runpod_result.py runpod_rtx5090_10s_response.json --mode benchmark
```

The inspector estimates 10-second hit probability and required worker count for full TRON Base58 prefix2 + suffix5:

```text
58^6 = 38,068,692,544
```

## Stop Conditions

Stop immediately if:

- validation does not pass,
- benchmark output contains forbidden key names,
- `benchmark_result.addresses_per_second` is missing,
- output reports hash speed instead of complete TRON address attempts,
- RunPod logs or output expose token, secret, mnemonic, seed, or private key material.

If speed is far below target, the next engineering step is CUDA core optimization, not using 47.80.70.211 as a test machine.
