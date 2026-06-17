# RunPod GPU Pod Result Template

Use this template to record the next normal GPU Pod check. Do not include private keys, tokens, RunPod API keys, customer patterns, or customer data.

## Pod

- GPU model:
- CUDA arch used:
- RunPod pod id:
- Started at:
- Stopped at:
- Repo commit:

## Vector Gate

Command:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Required markers:

- `tron_gpu_address_layer_passed`:
- `tron_gpu_address_layer_script_passed`:
- `tron_gpu_vector_fields_verified`:

Required per-vector fields:

- `xy_payload_passed` all true:
- `prefix_possible_passed` all true:
- `wrong_prefix_possible_rejected` all true:
- `prefix_prefilter_passed` all true:
- `wrong_prefix_prefilter_rejected` all true:
- `suffix_prefilter_passed` all true:
- `wrong_suffix_prefilter_rejected` all true:

Decision:

- If any field is false or missing, do not run smoke or benchmark.

## Smoke

Command:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_SMOKE=1 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Required marker:

- `tron_gpu_pattern_smoke_passed`:

Decision:

- If smoke fails, do not run benchmark.

## 3 Second Benchmark

Command:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_BENCHMARK=1 \
BENCHMARK_SECONDS=3 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Benchmark JSON fields:

- `candidate_attempts_per_second_estimate`:
- `reported_gpu_mkey_s`:
- `samples`:
- `timeout_reached`:
- `tron_gpu_pattern_benchmark_passed`:

Inspector summary:

- `expected_mean_seconds`:
- `p90_seconds`:
- `required_workers.mean_5s`:
- `required_workers.p90_8s`:

Decision:

- If output contains any sensitive marker, stop.
- If `candidate_attempts_per_second_estimate` is missing or below expectation, do not run longer benchmark until reviewed.

## 10 Second Benchmark

Run only after the 3 second benchmark is clean.

Command:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_BENCHMARK=1 \
BENCHMARK_SECONDS=10 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Benchmark JSON fields:

- `candidate_attempts_per_second_estimate`:
- `reported_gpu_mkey_s`:
- `samples`:
- `timeout_reached`:
- `tron_gpu_pattern_benchmark_passed`:

Inspector summary:

- `expected_mean_seconds`:
- `p90_seconds`:
- `required_workers.mean_5s`:
- `required_workers.p90_8s`:

## Review Decision

- Can proceed toward Serverless:
- Needs more CUDA optimization:
- Needs rollback:
- Notes:
