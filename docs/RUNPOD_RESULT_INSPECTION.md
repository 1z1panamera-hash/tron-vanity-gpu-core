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
- suffix-only probability and worker-count estimates.

## Capacity Math Only

To calculate worker count from a measured complete TRON address speed:

```bash
scripts/capacity_math.py --addresses-per-second 200000000 --seconds 8
```

The input must be complete TRON `addresses_per_second`, not hash speed.

The product rule is `suffix` only. Python maps it to full-address `prefix_len=0` plus `suffix_len=5` for the CUDA binary. The effective random space is `58^5`.

## VanitySearch Bounded Benchmark Signal

If the patched VanitySearch bounded benchmark prints mixed stdout plus JSON, save it locally and run:

```bash
scripts/inspect_vanitysearch_benchmark.py vanitysearch_benchmark_stdout.txt
```

The inspector reports:

- `candidate_attempts_per_second_estimate`
- single-worker 5 second and 8 second hit probability
- expected mean seconds
- P90 seconds
- speed required for mean <= 5 seconds
- speed required for P90 <= 8 seconds
- required worker count for both targets

This is only a GPU Pod direction signal. It is not final Serverless proof and it does not replace the eventual age-encrypted worker path.

Current VanitySearch patch note: TRON bounded benchmark counters are corrected to complete TRON address candidates per second. Do not compare older 6x-inflated VanitySearch Mkey/s output with the current `candidate_attempts_per_second_estimate`.

Current GPU address-layer note: the hot path uses direct x/y coordinate Keccak absorption. Trust bounded benchmark output only after the RunPod vector check reports `xy_payload_passed=true` for every public TEST_ONLY vector.

Current suffix-only note: the hot path must still compute checksum correctly before judging the final 5 Base58Check characters. Trust benchmark output only after the RunPod vector check reports suffix fields true for every public TEST_ONLY vector.

Current RunPod gate note: `scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh` parses the vector JSON and must print `tron_gpu_vector_fields_verified` before any smoke or bounded benchmark output is considered usable.

## Find Response

After a controlled `mode=find` test returns, save the full RunPod response JSON locally, for example:

```text
runpod_find_response.json
```

Then run:

```bash
scripts/inspect_runpod_result.py runpod_find_response.json --mode find
```

The inspector checks:

- response mode is `find`,
- `matched = true`,
- `matched_address` is a reasonable TRON Base58 address,
- `matched_address` ends with the requested 5-character suffix,
- `match_rule.prefix_len = 0`,
- `match_rule.suffix_len = 5`,
- `match_rule.search_space = 58^5`,
- `encrypted_private_key` is age armor,
- no forbidden raw key or credential fields are present.

If this fails, do not continue to repeated Serverless tests.

## Serverless Find E2E Batch

For cold/warm timing proof, save one cold response and at least ten warm responses under a local ignored directory:

```text
serverless_find_e2e/find_00.json
serverless_find_e2e/find_01.json
...
serverless_find_e2e/find_10.json
```

If possible, include top-level `request_latency_seconds` in each saved JSON. If that field is missing, the inspector falls back to RunPod `executionTime` or worker `elapsed_seconds`.

Inspect the batch:

```bash
scripts/inspect_serverless_find_e2e.py serverless_find_e2e --cold-count 1
```

Required pass conditions:

- every sample passes the single find response inspector,
- at least 10 warm samples exist,
- warm average <= 5 seconds,
- warm P90 <= 8 seconds,
- cold start is reported separately.

## GPU Pod Sequence Result Directory

If the normal GPU Pod test was run through:

```bash
scripts/runpod_gpu_pod_sequence.sh
```

inspect the whole saved directory:

```bash
scripts/inspect_runpod_sequence_result.py runpod_results/<utc-run-id>
```

The sequence inspector checks the vector gate markers, optional smoke marker, optional benchmark markers, and benchmark inspector JSON. Its `decision` field tells whether to run smoke next, run a 3 second benchmark next, run a 10 second benchmark next, review the speed for Serverless, or stop and review failures.

## Safety

These scripts:

- do not connect to 47.80.70.211,
- do not call RunPod,
- do not build Docker,
- do not run CUDA,
- do not run benchmark.

They only parse local JSON files and print pass/fail summaries.
