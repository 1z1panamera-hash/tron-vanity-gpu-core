# RunPod Suffix-Only GPU Pod Next Test

Purpose: run the next paid GPU Pod test for the current product rule.

## Current Product Rule

- Match only the last 5 characters of the full TRON Base58Check address.
- Do not match any prefix after the fixed leading `T`.
- Example product input: `suffix = CDEFG`.
- Internal CUDA binary fields: `prefix_len = 0`, `suffix_len = 5`.
- Search space: `58^5 = 656,356,768`.
- Target: average <= 5 seconds and P90 <= 8 seconds.
- Required single-worker speed:
  - mean <= 5s: about `131.27M complete TRON addresses/s`
  - P90 <= 8s: about `188.91M complete TRON addresses/s`
- Engineering pass gate: at least `200M complete TRON attempts/s`
- Preferred speed before Serverless migration: `300M+ complete TRON attempts/s`

The last 5 Base58Check characters depend on checksum. A candidate is valid only after the CUDA/C++ path computes:

```text
private scalar -> secp256k1 public key -> Keccak-256 -> TRON payload21 -> double-SHA256 checksum -> Base58Check -> suffix match
```

Hash-only speed is not valid evidence.

## Safety

- Do not run this on `47.80.70.211`.
- Use a normal RunPod GPU Pod for development and benchmark, not Serverless yet.
- Do not use customer suffixes or customer data.
- Keep `TRON_SUPPRESS_SECRET_OUTPUT=1` for bounded VanitySearch tests.
- Do not output plaintext key material.
- Do not continue to Serverless during the speed sprint.
- Age/find delivery work is paused until the GPU path is stable above the `200M attempts/s` engineering minimum.

## Expected Repository State

Clone the public repo on the GPU Pod:

```bash
git clone https://github.com/1z1panamera-hash/tron-vanity-gpu-core.git
cd tron-vanity-gpu-core
git rev-parse HEAD
```

Expected current minimum commit:

```text
0a9e98d167eb3a2b6b26b62d0df774d462232d23
```

If the commit is older, stop and update the Pod checkout.

## Recommended Sequence

Use the sequence script so each stage is saved under `runpod_results/<utc-run-id>/`.

To print the exact command sequence from the current repository commit:

```bash
scripts/print_runpod_suffix_only_commands.sh
```

This helper only prints commands. It does not call RunPod or run CUDA.

## Current Speed Sprint Path

Use the one-command speed test after the vector gate is known to pass on the selected GPU image. It runs the speed sweep and immediately inspects the saved result:

```bash
ALLOW_RUNPOD_SUFFIX_SPEED_TEST=1 CUDA_ARCH=sm_80 BENCHMARK_SECONDS=3 \
  scripts/runpod_gpu_pod_suffix_speed_test.sh
```

The lower-level speed sweep remains available if you want to run the sweep without automatic inspection:

```bash
ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1 CUDA_ARCH=sm_80 BENCHMARK_SECONDS=3 \
  scripts/runpod_gpu_pod_suffix_speed_sweep.sh
```

Default sweep dimensions:

```text
SWEEP_STEP_SIZES="1024 2048 4096"
SWEEP_GRIDS="8,128 16,128 32,128 64,128 128,128"
```

For H100 or a Blackwell image without native Blackwell CUDA support, start with `CUDA_ARCH=sm_90`. If the CUDA image supports the native Blackwell architecture, test that separately and record the image tag.

Optional profiler run:

```bash
ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1 CUDA_ARCH=sm_80 BENCHMARK_SECONDS=3 \
RUN_NSYS=1 PROFILE_STEP_SIZE=4096 PROFILE_GRID=64,128 PROFILE_SECONDS=5 \
  scripts/runpod_gpu_pod_suffix_speed_sweep.sh
```

The sweep writes:

```text
runpod_results/suffix_speed_sweep_<utc-run-id>/speed_sweep_summary.json
runpod_results/suffix_speed_sweep_<utc-run-id>/nvidia_smi_initial.txt
runpod_results/suffix_speed_sweep_<utc-run-id>/gpu_utilization.csv
runpod_results/suffix_speed_sweep_<utc-run-id>/build_step_<STEP_SIZE>.stdout.txt
```

Inspect the saved sweep result:

```bash
scripts/inspect_suffix_speed_sweep.py runpod_results/suffix_speed_sweep_<utc-run-id>
```

Important decisions:

- `increase_batch_or_fix_gpu_utilization`: GPU utilization is low; adjust `STEP_SIZE`, grid, or occupancy before deeper algorithm work.
- `optimize_secp256k1_or_address_hot_path`: GPU is working, but speed is still below `200M`.
- `engineering_min_passed_continue_toward_300m`: minimum speed passed; continue toward preferred `300M+`.
- `preferred_speed_passed_profile_before_serverless`: speed is good enough to profile stability before Serverless work resumes.

The inspector also parses `ptxas` build output where available. Register count or spill warnings are useful evidence for the next CUDA optimization pass.

Speed targets:

- Minimum engineering pass: `200M attempts/s`
- Preferred buffer: `300M+ attempts/s`

If the best `STEP_SIZE + grid` pair is still below `200M`, keep optimizing the CUDA hot path before spending on Serverless. The first bottleneck to inspect is secp256k1 point walking and point addition throughput. If `gpu_utilization.csv` shows low GPU utilization, increase grid/batch or inspect launch/occupancy before changing higher-level product code.

### 1. Vector Gate Only

```bash
CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Required result:

```text
tron_gpu_address_layer_passed
tron_gpu_address_layer_script_passed
tron_gpu_vector_fields_verified
```

Stop if this fails.

### 2. Startup Smoke

```bash
RUN_SMOKE=1 CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Required result:

```text
tron_gpu_pattern_smoke_passed
```

Stop if this fails.

### 3. Three-Second Benchmark

```bash
RUN_SMOKE=1 RUN_BENCHMARK_3=1 CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Inspect:

```bash
scripts/inspect_runpod_sequence_result.py runpod_results/<utc-run-id>
```

Stop if there are failures or sensitive markers.

### 4. Ten-Second Benchmark

Only after the three-second benchmark is clean:

```bash
RUN_SMOKE=1 RUN_BENCHMARK_3=1 RUN_BENCHMARK_10=1 CUDA_ARCH=sm_80 scripts/runpod_gpu_pod_sequence.sh
```

Inspect:

```bash
scripts/inspect_runpod_sequence_result.py runpod_results/<utc-run-id>
```

Record the result with:

```text
docs/RUNPOD_GPU_POD_RESULT_TEMPLATE.md
```

## Decision

Can move toward Serverless only if:

- vector gate passes,
- smoke passes,
- benchmark output contains no forbidden key markers,
- speed is at least `200M complete TRON attempts/s`,
- `300M+ complete TRON attempts/s` is preferred before Serverless migration,
- `nvidia-smi` or profiler evidence shows high GPU utilization,
- the speed path has been profiled and remains stable under repeated short GPU Pod runs.

If speed is below target, continue CUDA hot-path optimization before spending on Serverless.

During the current speed sprint, do not add age encryption or production find response logic. That work resumes only after the speed path is stable above the `200M attempts/s` engineering minimum.

The sequence inspector reports this as:

```text
decision = speed_gate_passed_continue_profiling
```

If it reports:

```text
decision = optimize_cuda_before_serverless
```

do not create a Serverless endpoint yet.
