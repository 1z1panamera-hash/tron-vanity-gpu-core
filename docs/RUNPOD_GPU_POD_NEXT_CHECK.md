# RunPod GPU Pod Next Check

Purpose: run the next VanitySearch TRON GPU verification on a normal RunPod GPU Pod before any Serverless migration.

Do not run these commands on `47.80.70.211`.
Do not use customer patterns or customer data.
Do not set long benchmark durations until the vector gate passes.

## 1. Clone Latest Main

```bash
git clone https://github.com/1z1panamera-hash/tron-vanity-gpu-core.git
cd tron-vanity-gpu-core
git rev-parse HEAD
```

Expected: the printed commit must match GitHub `main` at the time of the RunPod test. Record it with the benchmark result.

## Recommended Sequence Script

Default vector gate only:

```bash
CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Vector gate plus startup smoke:

```bash
RUN_SMOKE=1 CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Vector gate, smoke, and 3 second benchmark:

```bash
RUN_SMOKE=1 RUN_BENCHMARK_3=1 CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Vector gate, smoke, 3 second benchmark, and 10 second benchmark:

```bash
RUN_SMOKE=1 RUN_BENCHMARK_3=1 RUN_BENCHMARK_10=1 CUDA_ARCH=sm_80 \
  scripts/runpod_gpu_pod_sequence.sh
```

The script writes stdout and inspector files under `runpod_results/<utc-run-id>/`. That directory is ignored by git.

After each run, inspect the whole result directory locally:

```bash
scripts/inspect_runpod_sequence_result.py runpod_results/<utc-run-id>
```

Use the `decision` field to decide the next step. If it says `stop_and_review_failures`, do not continue to smoke or benchmark.

## 2. Vector Gate Only

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Required markers:

```text
tron_gpu_address_layer_passed
tron_gpu_address_layer_script_passed
tron_gpu_vector_fields_verified
```

Do not run benchmark if any marker is missing.

## 3. Short Startup Smoke

Only after the vector gate passes:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_SMOKE=1 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Required extra marker:

```text
tron_gpu_pattern_smoke_passed
```

## 4. Bounded Benchmark

Only after vector gate and smoke pass. Start with 3 seconds:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_BENCHMARK=1 \
BENCHMARK_SECONDS=3 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

If the 3 second result is clean, run 10 seconds:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_BENCHMARK=1 \
BENCHMARK_SECONDS=10 CUDA_ARCH=sm_80 \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Required extra marker:

```text
tron_gpu_pattern_benchmark_passed
```

Save the full stdout locally and inspect it with:

```bash
scripts/inspect_vanitysearch_benchmark.py vanitysearch_benchmark_stdout.txt
```

If the benchmark was produced by `scripts/runpod_gpu_pod_sequence.sh`, prefer inspecting the whole directory:

```bash
scripts/inspect_runpod_sequence_result.py runpod_results/<utc-run-id>
```

Record the result using:

```text
docs/RUNPOD_GPU_POD_RESULT_TEMPLATE.md
```

## Safety Boundary

- The bounded benchmark uses `TRON_SUPPRESS_SECRET_OUTPUT=1`.
- Benchmark patterns must be test patterns only, for example `TA*CDEFG`.
- The reported rate must be treated as complete TRON address candidates per second, not hash speed.
- This is still GPU Pod evidence, not Serverless P90 proof.
