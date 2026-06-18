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

If using the gated E2E runner, it saves the repeated find responses for you:

```bash
scripts/runpod_serverless_find_e2e.py \
  --dry-run \
  --endpoint-id "$RUNPOD_ENDPOINT_ID" \
  --age-recipient "$TEST_AGE_RECIPIENT" \
  --suffix CDEFG \
  --samples 11 \
  --cold-count 1
```

```bash
ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1 \
  scripts/runpod_serverless_find_e2e.py \
  --endpoint-id "$RUNPOD_ENDPOINT_ID" \
  --suffix CDEFG \
  --age-recipient "$TEST_AGE_RECIPIENT" \
  --samples 11 \
  --cold-count 1 \
  --out-dir serverless_find_e2e
```

`RUNPOD_API_KEY` must be set in the environment for that command. Do not write the key into any repository file.

For the first paid smoke, use one sample only and inspect it as a single find response:

```bash
ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1 \
  scripts/runpod_serverless_find_e2e.py \
  --endpoint-id "$RUNPOD_ENDPOINT_ID" \
  --age-recipient "$TEST_AGE_RECIPIENT" \
  --suffix CDEFG \
  --samples 1 \
  --cold-count 0 \
  --allow-short-smoke \
  --out-dir serverless_find_smoke

scripts/inspect_runpod_result.py serverless_find_smoke/find_00.json --mode find
```

Optional local age-envelope check for test identities only:

```bash
scripts/verify_age_encrypted_find_response.py \
  serverless_find_smoke/find_00.json \
  --identity "<local-test-age-identity-file>"
```

The verifier confirms that the returned age armor decrypts to the expected
payload shape, but it does not print decrypted key material. Never store a
customer age identity in this repo or on `47.80.70.211`.

For cold/warm batches that all use the same test recipient, the batch inspector
can also verify every age envelope:

```bash
scripts/inspect_serverless_find_e2e.py \
  serverless_find_e2e \
  --cold-count 1 \
  --age-identity "<local-test-age-identity-file>"
```

Short smoke is not P90 evidence. It only proves the endpoint, CUDA worker, JSON hit path, and age envelope return are wired.
