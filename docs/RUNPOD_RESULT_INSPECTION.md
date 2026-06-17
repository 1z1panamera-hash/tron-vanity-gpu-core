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

The product rule is `prefix_after_t` plus `suffix`. Python maps it to full-address `prefix_len=2` plus `suffix_len=5` for the CUDA binary. Because normal TRON addresses have fixed leading `T`, the effective random space is `58^6`.

## VanitySearch Bounded Benchmark Signal

If the patched VanitySearch bounded benchmark prints mixed stdout plus JSON, save it locally and run:

```bash
scripts/inspect_vanitysearch_benchmark.py vanitysearch_benchmark_stdout.txt
```

The inspector reports:

- `candidate_attempts_per_second_estimate`
- single-worker 10 second and 15 second hit probability
- expected mean seconds
- P90 seconds
- speed required for mean <= 10 seconds
- speed required for P90 <= 15 seconds
- required worker count for both targets

This is only a GPU Pod direction signal. It is not final Serverless proof and it does not replace the eventual age-encrypted worker path.

## Safety

These scripts:

- do not connect to 47.80.70.211,
- do not call RunPod,
- do not build Docker,
- do not run CUDA,
- do not run benchmark.

They only parse local JSON files and print pass/fail summaries.
