# RunPod Result Inspection

Date: 2026-06-17

Purpose: inspect RunPod JSON output without calling RunPod and without relying on chat memory.

## Validate Response

Save the RunPod response JSON to a local file, for example:

```text
runpod_validate_response.json
```

Then run:

```bash
scripts/inspect_runpod_result.py runpod_validate_response.json --mode validate_vectors
```

Required pass conditions:

- `mode = validate_vectors`
- `phase0_vectors.passed = true`
- `compile.ready = true`
- `gpu_binary.returncode = 0`
- `passed = true`
- no forbidden keys: `private_key`, `mnemonic`, `seed`, `token`, `secret`

If this fails, do not run benchmark.

## Benchmark Response

Only after validation passes and the RunPod endpoint explicitly has:

```text
ALLOW_GPU_BENCHMARK=1
```

inspect benchmark output:

```bash
scripts/inspect_runpod_result.py runpod_benchmark_response.json --mode benchmark
```

The inspector checks:

- response mode,
- `benchmark_result`,
- `attempts`,
- `addresses_per_second`,
- `keys_per_second`,
- `kernel_mode`; accepted values are `incremental_public_key_walk` and `scalar_multiply_per_candidate`,
- `gpu_name`,
- forbidden key leakage,
- 10 second probability and worker-count estimates.

## Capacity Math Only

To calculate worker count from a measured complete TRON address speed:

```bash
scripts/capacity_math.py --addresses-per-second 1000000000 --seconds 10
```

The input must be complete TRON `addresses_per_second`, not hash speed.

## Safety

These scripts:

- do not connect to 47.80.70.211,
- do not call RunPod,
- do not build Docker,
- do not run CUDA,
- do not run benchmark.

They only parse local JSON files and print pass/fail summaries.
