# RunPod GitHub Upload Checklist

RunPod GitHub authorization is active, but the console currently shows:

```text
Select a repo
No repos found
```

That means the prepared local repository is not yet visible to RunPod.

## Current Repository To Upload

```text
/Users/1z1/Documents/Codex/服务器/47.80.70.211/工作记录/tron-vanity-gpu-core-github-repo
```

Latest required commit at the time this checklist was written:

```text
3a78c517b6e3621f687b9dea8a538ce6cc7f52e1
```

## Recommended GitHub Repository

```text
tron-vanity-gpu-core
```

Public is the simplest option because the RunPod console currently exposes a `Public only` filter and returned no repositories. If a private repository is used, the RunPod GitHub app must be explicitly granted access to that repository.

## Before Upload

Run:

```bash
scripts/public_repo_audit.py
scripts/local_preflight.sh
```

Both must pass.

Optional dry-run helper after the GitHub repository exists:

```bash
scripts/prepare_github_push.sh --repo-url https://github.com/OWNER/tron-vanity-gpu-core.git
```

The helper does not push unless `--push` is passed.

## Upload Rules

- Do not upload `.env`.
- Do not upload RunPod API keys.
- Do not upload Docker Hub tokens.
- Do not upload `runpod_*_response.json` or `runpod_*_inspect.json`.
- Do not upload private customer data.
- The only private-key-looking values allowed in this repository are the public TEST_ONLY values in `tests/phase0_test_vectors.json`.

## RunPod After Upload

In RunPod:

```text
Serverless -> New Endpoint -> Custom deployment -> Deploy from GitHub
```

Select the uploaded repository.

Use:

```text
Dockerfile path: Dockerfile
Endpoint type: Queue
Environment: ALLOW_RUNTIME_NVCC=1
```

Do not set:

```text
ALLOW_GPU_BENCHMARK=1
```

First request must be:

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

Only after `validate_vectors` passes should benchmark mode be enabled.
