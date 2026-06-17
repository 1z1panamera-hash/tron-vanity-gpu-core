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
- Do not continue to Serverless until GPU Pod vector gate and speed evidence are clean.

## Expected Repository State

Clone the public repo on the GPU Pod:

```bash
git clone https://github.com/1z1panamera-hash/tron-vanity-gpu-core.git
cd tron-vanity-gpu-core
git rev-parse HEAD
```

Expected current minimum commit:

```text
94aef3d8b429020d98a4e6f337a0e099447b9e06
```

If the commit is older, stop and update the Pod checkout.

## Recommended Sequence

Use the sequence script so each stage is saved under `runpod_results/<utc-run-id>/`.

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
- speed is at least `188.91M complete TRON addresses/s` for single-worker P90 <= 8 seconds, or sharding math is explicitly accepted,
- production `find` path returns only `matched_address` and `encrypted_private_key`.

If speed is below target, continue CUDA hot-path optimization before spending on Serverless.

The sequence inspector reports this as:

```text
decision = serverless_speed_gate_passed_pending_find_validation
```

If it reports:

```text
decision = optimize_cuda_before_serverless
```

do not create a Serverless endpoint yet.
