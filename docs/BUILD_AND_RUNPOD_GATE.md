# Build And RunPod Gate

Current status: suffix-only GPU Pod speed has passed; Serverless build and find E2E are the next gates.

Preferred build/deploy path is RunPod GitHub integration, documented in `docs/RUNPOD_GITHUB_DEPLOY_PATH.md`, because local Docker is unavailable and `47.80.70.211` is not allowed to build images, compile CUDA, or run benchmarks.

## Allowed Later Only After Confirmation

- Build Docker image.
- Push image to a registry.
- Create or update RunPod Serverless endpoint.
- Call RunPod API.
- Run GPU benchmark or find E2E.

## Current Build Target

The image must build the patched VanitySearch TRON suffix-only worker:

```text
/app/build/vanitysearch_tron_worker
```

The Dockerfile invokes `scripts/build_vanitysearch_tron_worker.sh`, which verifies the patch hash before building.

## First Serverless Smoke Target

Use only a test suffix and a test age recipient. Product payloads use `suffix`; they must not use `prefix_len`, `suffix_len`, or `prefix_after_t`.

```json
{
  "input": {
    "mode": "find",
    "suffix": "CDEFG",
    "age_recipient": "age1_replace_with_valid_test_recipient",
    "duration_seconds": 15,
    "max_attempts": 10000000000,
    "gpu_grid": "128,128"
  }
}
```

The placeholder recipient is not valid. Replace it with a generated test recipient before any paid RunPod call.

Inspect the saved response locally:

```bash
scripts/inspect_runpod_result.py serverless_find_smoke/find_00.json --mode find
```

If the matching test identity is available locally, also verify the age envelope:

```bash
scripts/verify_age_encrypted_find_response.py \
  serverless_find_smoke/find_00.json \
  --identity "<local-test-age-identity-file>"
```

The verifier must not print decrypted key material.

## Cold/Warm E2E Target

After one smoke response passes, run a controlled E2E set:

```bash
ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1 \
  scripts/runpod_serverless_find_e2e.py \
  --endpoint-id "<endpoint-id>" \
  --age-recipient "<test-age-recipient>" \
  --suffix CDEFG \
  --samples 11 \
  --cold-count 1 \
  --out-dir serverless_find_e2e
```

Then inspect:

```bash
scripts/inspect_serverless_find_e2e.py serverless_find_e2e --cold-count 1
```

## Pass Criteria

Serverless can move toward production integration only if:

- The image builds from the current GitHub repo.
- The image contains the patched VanitySearch TRON suffix-only worker.
- `find` returns `matched: true`, `matched_address`, and `encrypted_private_key`.
- The matched address ends with the requested 5-character suffix.
- The response does not contain plaintext `private_key`, WIF, or raw VanitySearch output.
- Benchmark output does not contain token, secret, seed, or mnemonic.
- Warm Serverless average latency is <= 5 seconds.
- Warm Serverless P90 latency is <= 8 seconds.
- Cold start latency is measured and reported separately.

## Current Limitation

Normal GPU Pod speed evidence is strong, but Serverless cold/warm latency is still unproven.
Do not claim production-ready until the Serverless E2E gate passes.
