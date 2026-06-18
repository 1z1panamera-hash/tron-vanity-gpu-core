# RunPod Response Intake

Use this after the first RunPod `validate_vectors` request returns.

## Save Location

Save the full RunPod response JSON in the repository root as:

```text
runpod_validate_response.json
```

This file is intentionally ignored by git.

Do not save API keys, tokens, private keys, secrets, or `.env` content.

## Local Inspection

From the repository root:

```bash
scripts/inspect_runpod_result.py runpod_validate_response.json --mode validate_vectors
```

Optional: save the inspection summary locally:

```bash
scripts/inspect_runpod_result.py runpod_validate_response.json --mode validate_vectors > runpod_validate_inspect.json
```

`runpod_validate_inspect.json` is also ignored by git.

## Pass Gate

Continue only if the inspection output has:

```text
passed = true
failures = []
forbidden_key_paths = []
```

The summary must show:

```text
phase0_vectors_passed = true
compile_ready = true
gpu_binary_returncode = 0
passed = true
```

If any check fails, do not run benchmark. Use `docs/RUNPOD_VALIDATE_TROUBLESHOOTING.md`.

## Next File Names

After validation passes, save later benchmark responses as:

```text
runpod_benchmark_smoke_response.json
runpod_a100_10s_response.json
runpod_rtx5090_10s_response.json
runpod_find_response.json
```

These files are ignored by git. They are local evidence files, not repository artifacts.

For repeated Serverless find timing, save local evidence under:

```text
serverless_find_e2e/
```

This directory is also ignored by git.

Inspect find evidence with:

```bash
scripts/inspect_runpod_result.py runpod_find_response.json --mode find
scripts/inspect_serverless_find_e2e.py serverless_find_e2e --cold-count 1
```
