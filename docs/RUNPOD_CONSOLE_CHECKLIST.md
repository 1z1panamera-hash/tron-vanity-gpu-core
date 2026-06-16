# RunPod Console Checklist

Date: 2026-06-17

Purpose: minimal console checklist for the first RunPod Serverless validation. This is not a benchmark checklist.

## Before Opening RunPod

Local package must already pass:

```bash
scripts/local_preflight.sh
```

Expected final line:

```text
local_preflight_passed
```

## GitHub Repository

Create or update a GitHub repository with the contents of this directory.

Repository root must contain:

- `Dockerfile`
- `app.py`
- `requirements.txt`
- `src/`
- `tests/phase0_test_vectors.json`
- `RUNPOD_VALIDATE_PAYLOAD.json`

Do not commit:

- `.env`
- API key
- token
- secret
- private key
- Docker password

## RunPod Endpoint Creation

In RunPod Console:

1. Go to Serverless.
2. Create new endpoint.
3. Choose GitHub integration.
4. Select the GitHub repository and branch.
5. Dockerfile path:

```text
Dockerfile
```

6. Endpoint type:

```text
Queue
```

7. Worker environment variables:

```text
ALLOW_RUNTIME_NVCC=1
```

Do not add:

```text
ALLOW_GPU_BENCHMARK=1
```

8. Pick a low-cost CUDA-capable GPU for the first validation if RunPod gives a choice.
9. Create the endpoint and wait for build/deploy logs.

## First Request

Use `RUNPOD_VALIDATE_PAYLOAD.json`:

```json
{
  "input": {
    "mode": "validate_vectors"
  },
  "policy": {
    "executionTimeout": 300000,
    "ttl": 900000
  }
}
```

Do not send the benchmark payload yet.

## Copy Result Back

Save the RunPod response JSON locally as:

```text
runpod_validate_response.json
```

Then inspect:

```bash
scripts/inspect_runpod_result.py runpod_validate_response.json --mode validate_vectors
```

Only continue if it passes.

## Do Not Do In First Run

- Do not set `ALLOW_GPU_BENCHMARK=1`.
- Do not run `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`.
- Do not use 47.80.70.211 for build or testing.
- Do not paste RunPod API key into files.
- Do not paste Docker password into files.
- Do not return or save real private keys.

## After Validation Passes

Only after the local inspector passes:

1. Decide whether to enable `ALLOW_GPU_BENCHMARK=1`.
2. Run the small benchmark smoke payload.
3. Inspect the benchmark JSON locally.
4. Then decide A100 and RTX 5090 short tests.
