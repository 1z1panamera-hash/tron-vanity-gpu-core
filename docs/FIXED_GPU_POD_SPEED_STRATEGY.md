# Fixed GPU Pod Speed Strategy

Date: 2026-06-19 Asia/Shanghai

Purpose: keep the suffix-only TRON worker fast and cheap when Serverless queue
or cold-start behavior is not acceptable.

## Current Recommendation

Do not depend on RTX 3090 / 4090 / 5090 availability. On RunPod these consumer
cards may be difficult to rent consistently. Treat them as opportunistic low
cost options, not the primary production plan.

Primary fixed-Pod candidates:

- RTX PRO 6000 / Blackwell / 96 GB class: fastest observed path so far.
- H100 / H200: likely available more often than consumer cards; must be tested.
- A100: fallback high-end baseline; slower than Blackwell in earlier tests but
  broadly supported.

Opportunistic candidates:

- RTX 4090: test when available.
- RTX 3090: cheap but often unavailable; use only if inventory is stable.
- RTX 5090: attractive if available, but inventory may be limited.

## Native CUDA Architecture Builds

For fixed GPU Pods, prefer single-architecture builds instead of a fat binary.
This reduces build output size and avoids carrying unused cubins.

Use:

```bash
ALLOW_RUNPOD_SUFFIX_AUTOTUNE=1 BENCHMARK_SECONDS=3 \
  scripts/runpod_gpu_pod_suffix_autotune.sh
```

The script detects `nvidia-smi` and selects:

- A100: `sm_80`
- RTX 3090: `sm_86`
- RTX 4090: `sm_89`
- H100 / H200: `sm_90`
- RTX 5090 / RTX PRO 6000 / Blackwell: `sm_120`

It also passes `CUDA_ARCHS=<same single arch>` to the build path so the test is
not using the Serverless fallback fat binary.

## Serverless vs Fixed Pod

Serverless:

- Best when traffic is sparse and occasional cold starts are acceptable.
- Use multi-GPU fallback to reduce unavailable-worker queue time.
- Keep `Active workers = 0` unless the user explicitly accepts idle cost.

Fixed Pod:

- Best when cold start and GPU allocation delays are unacceptable.
- Best for repeated customer tests or production batches.
- Use native single-architecture builds and keep the worker warm.

## Evidence Requirements

For each candidate GPU, record:

- GPU name from `nvidia-smi`
- CUDA arch used
- best `STEP_SIZE`
- best grid
- complete TRON attempts/s
- expected mean seconds for suffix-only last 5
- expected P90 seconds for suffix-only last 5
- whether the output stayed key-safe

Do not compare hash speed with complete TRON address generation speed.
