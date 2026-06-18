# RunPod Serverless Endpoint Config

Date: 2026-06-18 Asia/Shanghai

Use this config only for controlled test deployment. Do not use customer data.

## Source

- GitHub repo: `https://github.com/1z1panamera-hash/tron-vanity-gpu-core`
- Branch: `main`
- Current readiness commit is printed by:

```bash
scripts/runpod_serverless_readiness_check.py
```

## Build

- Dockerfile path: `Dockerfile`
- The Dockerfile is multi-stage:
  - builder stage uses CUDA devel image and compiles patched VanitySearch TRON worker.
  - runtime stage uses CUDA runtime image and contains only Python handler, `age`,
    RunPod SDK, test vectors, and `/app/build/vanitysearch_tron_worker`.
  - runtime stage intentionally does not include `git`, `g++`, `make`, `nvcc`,
    source tree, patches, or build scripts.
- The default build creates a CUDA fat binary for `sm_80,sm_86,sm_89,sm_120`,
  so one Serverless image can run on A100-class, 3090/4090-class, and
  Blackwell/5090-class workers.
- Recommended first GPU target: RTX PRO 6000 Blackwell / 5090-class if available.
- Build args for Blackwell / 5090-class:

```text
CUDA_ARCH=sm_120
CUDA_ARCHS=sm_80,sm_86,sm_89,sm_120
STEP_SIZE=4096
```

- Build args for A100 fallback:

```text
CUDA_ARCH=sm_80
CUDA_ARCHS=sm_80,sm_86,sm_89,sm_120
STEP_SIZE=4096
```

The speed evidence `1.54328B attempts/s` came from RTX PRO 6000 Blackwell with
suffix-only last-5 matching. A100 Serverless performance must be measured
separately and should not be assumed equal.

## Current Endpoint Fallback Config

Updated: 2026-06-19 Asia/Shanghai.

Endpoint `mf8hnwrsf293e1` is configured with multiple GPU types for fallback:

- 96 GB Pro
- 24 GB
- 24 GB Pro

Scale settings observed after rollout:

- Active workers: 0
- Max workers: 3
- GPU count: 1
- Idle timeout: 5 seconds
- Auto scaling: Queue delay, scale up after 4 seconds

This keeps zero baseline spend while allowing RunPod to choose from more than
one GPU type when the primary type has limited capacity. Active workers were
not enabled.

This fallback setup is for availability, not guaranteed maximum speed. If
Serverless cold start or allocation delay is unacceptable, use a normal fixed
GPU Pod and run `scripts/runpod_gpu_pod_suffix_autotune.sh` so the worker is
compiled for the exact GPU class.

## Runtime Environment Variables

Required:

```text
ALLOW_GPU_FIND=1
GPU_WORKER_BACKEND=vanitysearch
```

Do not set or store:

```text
RUNPOD_API_KEY
TEST_AGE_RECIPIENT
AGE identity / decrypt key
customer token
customer secret
private key material
```

`age_recipient` must be supplied in each test request payload. The customer or
test decrypt identity must stay outside the worker and outside `47.80.70.211`.

## Test Recipient

Generate a local test recipient only on the client machine that will inspect the
test response:

```bash
age-keygen -o /tmp/tron_vanity_test_age_identity.txt
```

Or generate the temporary test recipient and smoke payload together:

```bash
scripts/prepare_runpod_smoke_test_materials.py \
  --out-dir /tmp/tron_vanity_runpod_smoke \
  --endpoint-id "<endpoint-id>"
```

If `age-keygen` is not installed locally but you already have a test recipient,
generate only the payload and command files:

```bash
scripts/prepare_runpod_smoke_test_materials.py \
  --out-dir /tmp/tron_vanity_runpod_smoke \
  --endpoint-id "<endpoint-id>" \
  --age-recipient "<test-age-recipient>"
```

If neither `age-keygen` nor a recipient is available, generate test-only age
material with the built-in helper:

```bash
scripts/prepare_runpod_smoke_test_materials.py \
  --out-dir /tmp/tron_vanity_runpod_smoke \
  --endpoint-id "<endpoint-id>" \
  --python-age-keygen
```

Use the printed `age1...` recipient in the RunPod request payload. Keep the
identity file local and temporary. Never commit it and never copy it to
`47.80.70.211`.

## Pre-Flight Commands

Run locally before creating/updating the endpoint:

```bash
scripts/runpod_serverless_readiness_check.py
scripts/runpod_serverless_find_e2e.py \
  --dry-run \
  --endpoint-id "<endpoint-id>" \
  --age-recipient "<test-age-recipient>" \
  --suffix CDEFG \
  --samples 11 \
  --cold-count 1
```

Dry-run does not read the RunPod API key and does not call RunPod.

## First Paid Smoke

Only after the endpoint builds successfully:

```bash
ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1 \
  scripts/runpod_serverless_find_e2e.py \
  --endpoint-id "<endpoint-id>" \
  --age-recipient "<test-age-recipient>" \
  --suffix CDEFG \
  --samples 1 \
  --cold-count 0 \
  --allow-short-smoke \
  --out-dir serverless_find_smoke
```

Inspect:

```bash
scripts/inspect_runpod_result.py serverless_find_smoke/find_00.json --mode find
scripts/verify_age_encrypted_find_response.py \
  serverless_find_smoke/find_00.json \
  --identity /tmp/tron_vanity_test_age_identity.txt
```

## Cold/Warm E2E

Run only after the smoke response passes:

```bash
export RUNPOD_ENDPOINT_ID="<endpoint-id>"
export RUNPOD_API_KEY="<do-not-save-this-in-files>"
export TEST_AGE_RECIPIENT="<test-age-recipient>"

ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1 \
  scripts/runpod_serverless_find_e2e.py \
  --suffix CDEFG \
  --samples 11 \
  --cold-count 1 \
  --out-dir serverless_find_e2e

scripts/inspect_serverless_find_e2e.py \
  serverless_find_e2e \
  --cold-count 1 \
  --age-identity /tmp/tron_vanity_test_age_identity.txt
```

Pass target:

- warm average <= 5 seconds
- warm P90 <= 8 seconds
- cold start measured separately
- every response has age ciphertext only
- no plaintext key material in response files
