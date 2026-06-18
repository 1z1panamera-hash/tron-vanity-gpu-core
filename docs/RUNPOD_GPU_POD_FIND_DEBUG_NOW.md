# RunPod GPU Pod Find Debug

Purpose: debug suffix-only benchmark and find on a normal RunPod GPU Pod before returning to Serverless.

Do not run this on `47.80.70.211`.

Current priority:

- Run a short real benchmark.
- Derive a fixed-seed target suffix from a known candidate.
- Run a fixed-seed must-hit GPU find.
- Confirm whether the patched VanitySearch JSON hit path works.

Suggested Pod:

- Template: CUDA devel image such as `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`.
- Disk: 20 GB is enough for this debug pass.
- GPU: use the cheapest available GPU that can compile/run CUDA first; use RTX PRO 6000/5090-class only when checking speed.

Commands:

```bash
git clone https://github.com/1z1panamera-hash/tron-vanity-gpu-core.git
cd tron-vanity-gpu-core
git rev-parse HEAD
nvidia-smi

ALLOW_RUNPOD_FIND_DEBUG=1 \
CUDA_ARCH=sm_120 \
STEP_SIZE=4096 \
BENCHMARK_SECONDS=3 \
FIND_SECONDS=5 \
scripts/runpod_gpu_pod_find_debug.sh
```

For A100, use:

```bash
ALLOW_RUNPOD_FIND_DEBUG=1 \
CUDA_ARCH=sm_80 \
STEP_SIZE=4096 \
BENCHMARK_SECONDS=3 \
FIND_SECONDS=5 \
scripts/runpod_gpu_pod_find_debug.sh
```

Expected result files:

- `runpod_results/find_debug_<RUN_ID>/benchmark_summary.json`
- `runpod_results/find_debug_<RUN_ID>/fixed_seed_probe.json`
- `runpod_results/find_debug_<RUN_ID>/find_debug_summary.json`

Pass criteria:

- vector gate passes;
- benchmark summary contains a positive `candidate_attempts_per_second_estimate`;
- fixed seed find summary has `passed=true`;
- `matched=true`;
- `matched_suffix_ok=true`;
- raw find stdout is erased after sanitized summary.

If fixed seed find fails:

- inspect `find_debug_summary.json`;
- check `debug_lines` for GPU `th_id`, `incr`, `endo`, `mode`, and reconstructed address;
- do not continue Serverless testing until this path is fixed.

