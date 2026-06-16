# RunPod Action Now

This is the current required external step. Local work and 47.80.70.211 cannot prove CUDA compile or GPU speed.

## Current Local Package

Repository root to upload to GitHub:

```text
/Users/1z1/Documents/Codex/服务器/47.80.70.211/工作记录/tron-vanity-gpu-core-github-repo
```

Archive, if uploading by tarball:

```text
/Users/1z1/Documents/Codex/服务器/47.80.70.211/工作记录/gpu_core_staging/tron-vanity-gpu-core-github-ready-20260617.tar.gz
```

Archive SHA-256:

```text
Recorded outside this repository in the local server 说明.md after packaging.
```

Latest local commit:

```text
Use git rev-parse HEAD in the repository root.
```

## RunPod Step 1 Only: Validate Vectors

Create a RunPod Serverless endpoint from GitHub integration.

Current console gate:

```text
RunPod currently requires GitHub authorization before repositories can be selected.
Docker registry deployment is blocked unless a pre-built image already exists.
RunPod Flash is a possible fallback, but it requires local install plus `flash login`, which stores a RunPod API key locally, so use it only after explicit user confirmation.
```

See:

```text
docs/RUNPOD_DEPLOYMENT_ROUTE_DECISION_20260617.md
```

Settings:

```text
Dockerfile path: Dockerfile
Endpoint type: Queue
Environment: ALLOW_RUNTIME_NVCC=1
```

Do not set:

```text
ALLOW_GPU_BENCHMARK=1
```

Do not use:

```text
RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json
RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json
RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json
```

First payload:

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

## Pass Criteria

Continue only if the RunPod response contains:

```text
mode = validate_vectors
phase0_vectors.passed = true
compile.ready = true
gpu_binary.returncode = 0
passed = true
```

Stop if any item fails.

## Save Result Back Locally

Save the full RunPod JSON response as:

```text
runpod_validate_response.json
```

Then inspect locally from the repository root:

```bash
scripts/inspect_runpod_result.py runpod_validate_response.json --mode validate_vectors
```

For file naming and local evidence handling, use `docs/RUNPOD_RESPONSE_INTAKE.md`.

Do not paste API keys, tokens, private keys, secrets, or `.env` contents into files.

## Next Gate

Only after validation passes:

1. enable `ALLOW_GPU_BENCHMARK=1`,
2. run `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`,
3. inspect the response locally,
4. then decide whether to run A100 and RTX 5090-class 10 second payloads.

47.80.70.211 must not build, compile CUDA, run benchmark, or brute-force addresses.
