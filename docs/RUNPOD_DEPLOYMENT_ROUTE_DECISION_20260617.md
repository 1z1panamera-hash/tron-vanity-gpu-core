# RunPod Deployment Route Decision - 2026-06-17

## Current State

The local GPU core repository is ready for the first RunPod validation gate, but no RunPod worker has been created yet.

First required remote gate:

```text
mode = validate_vectors
ALLOW_RUNTIME_NVCC=1
ALLOW_GPU_BENCHMARK not set
```

Do not run 10 second benchmark payloads until `validate_vectors` passes on RunPod.

## Routes Checked

### 1. RunPod Serverless GitHub integration

Status: preferred route.

RunPod console currently shows:

```text
Connect GitHub to deploy your repos
```

This route needs the user to authorize RunPod GitHub access. Codex must not click GitHub authorization or grant account access without explicit user action.

After GitHub is connected, use:

```text
Repository: tron-vanity-gpu-core-github-repo
Dockerfile path: Dockerfile
Endpoint type: Queue
Environment: ALLOW_RUNTIME_NVCC=1
```

Do not set:

```text
ALLOW_GPU_BENCHMARK=1
```

### 2. Docker registry / template

Status: blocked until an image exists.

RunPod console accepts a container image name, but this project has no pushed image.

Do not build Docker on `47.80.70.211`.
Do not use `47.80.70.211` as a Docker build host.
Do not push Docker images without explicit user confirmation.

### 3. RunPod Flash

Status: possible fallback, not current first route.

RunPod Flash can create Serverless GPU endpoints from local Python code, but it requires:

```text
pip install runpod-flash
flash login
```

`flash login` saves a RunPod API key locally. Codex must not read, print, or copy that key.

Flash is useful for simple Python remote GPU functions and may be useful for quick GPU environment probes. It is not yet proven as the best path for this repository's custom CUDA/C++ worker, because the target worker needs CUDA compilation and the existing RunPod Serverless handler/Dockerfile path is already prepared.

Fallback probe prepared:

```text
flash/runpod_flash_cuda_probe.py
docs/RUNPOD_FLASH_FALLBACK_PROBE.md
```

The probe defaults to no-op unless `--confirm-runpod-side-effect` is passed.

Use Flash only after explicit user confirmation, and only for a minimal probe first.

## Next Action

User action needed:

```text
RunPod console -> Serverless -> New Endpoint -> Custom deployment -> Deploy from GitHub -> Connect GitHub
```

After GitHub authorization, Codex can continue with configuration, but must stop before creating the endpoint if the action will create billable resources.

## Safety Rules

- Do not connect to or modify `47.80.70.211` for GPU work.
- Do not run benchmark on `47.80.70.211`.
- Do not build Docker on `47.80.70.211`.
- Do not run RunPod benchmark before `validate_vectors` passes.
- Do not output or save private keys.
- Do not read or output RunPod API keys, tokens, or secrets.
- Do not click authorization, deploy, create, or run buttons without action-time confirmation.
