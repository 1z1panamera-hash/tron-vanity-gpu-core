# RunPod Serverless Find E2E Next

Date: 2026-06-18 Asia/Shanghai

## Current State

- Suffix-only speed gate has passed on a normal RunPod GPU Pod.
- Best measured speed: about `1.54328B attempts/s` on RTX PRO 6000 Blackwell.
- Patched VanitySearch can emit an internal TRON JSON hit when `TRON_JSON_HIT_OUTPUT=1`.
- `app.py` can call the patched VanitySearch backend for `mode=find`.
- `app.py` returns only `matched_address`, `encrypted_private_key`, and non-sensitive metadata.

## Scope

This is the next paid RunPod validation stage.

Do not use:

- customer suffixes,
- customer age recipients,
- customer data,
- 47.80.70.211,
- local Mac Docker build.

Use only a test age recipient generated for this test.

## Required Precheck

Before creating or updating a Serverless endpoint:

1. Build the image from the current GitHub repo.
2. Confirm the image build compiles `/app/build/vanitysearch_tron_worker`.
3. Run a normal GPU Pod find smoke with an easy test suffix.
4. Confirm the worker response contains no raw key material markers.

## Test Payload Shape

Use this shape with a valid test age recipient:

```json
{
  "input": {
    "mode": "find",
    "suffix": "CDEFG",
    "age_recipient": "age1_replace_with_valid_test_recipient",
    "duration_seconds": 15,
    "max_attempts": 10000000000,
    "gpu_grid": "128,128"
  },
  "policy": {
    "executionTimeout": 300000,
    "ttl": 900000
  }
}
```

The placeholder recipient is not valid. Replace it before any RunPod test.

## Success Criteria

A successful response must include:

- `matched: true`
- `matched_address`
- `encrypted_private_key`
- `gpu_worker_backend: vanitysearch`
- no raw key material,
- no mnemonic,
- no seed,
- no token,
- no secret.

## Timing Test

Measure separately:

- cold start: first request after endpoint idle or new deployment,
- warm start: at least 10 repeated requests after the worker is already active.

Record:

- GPU type,
- image tag or repo commit,
- `duration_seconds`,
- `gpu_grid`,
- total request latency,
- worker reported `elapsed_seconds`,
- match success rate,
- warm average,
- warm P90,
- cold start latency.

## Save And Inspect

Save the first controlled find response as:

```text
runpod_find_response.json
```

Inspect it locally:

```bash
scripts/inspect_runpod_result.py runpod_find_response.json --mode find
```

## Optional Runner

After the Serverless endpoint exists and a valid test age recipient is available, the repository has a gated async runner:

Dry-run first. This validates inputs and prints the payload without reading the RunPod API key, calling RunPod, or writing response files:

```bash
scripts/runpod_serverless_find_e2e.py \
  --dry-run \
  --endpoint-id "<endpoint-id>" \
  --age-recipient "<test-age-recipient>" \
  --suffix CDEFG \
  --samples 11 \
  --cold-count 1
```

Then run one paid smoke request only after the dry-run payload is correct:

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

Inspect the smoke response:

```bash
scripts/inspect_runpod_result.py serverless_find_smoke/find_00.json --mode find
```

Only after smoke passes, run the full paid cold/warm E2E:

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
```

The runner uses RunPod async `/run` and polls `/status/<job_id>`. It does not use `/runsync`. It writes response JSON files under `serverless_find_e2e/`, which is ignored by git. The API key is read only from the environment and is not written to disk.

For repeated Serverless timing, save one cold response and at least ten warm responses:

```text
serverless_find_e2e/find_00.json
serverless_find_e2e/find_01.json
...
serverless_find_e2e/find_10.json
```

Add top-level `request_latency_seconds` to each saved JSON when measuring from the client side. If that is unavailable, the inspector falls back to RunPod `executionTime` or worker `elapsed_seconds`.

Inspect the batch:

```bash
scripts/inspect_serverless_find_e2e.py serverless_find_e2e --cold-count 1
```

## Do Not Claim Complete Until

- Serverless build succeeds from the current repo.
- The image contains the updated patch SHA.
- A GPU Pod find smoke proves the internal JSON hit path works.
- Serverless returns age ciphertext only.
- `scripts/inspect_runpod_result.py ... --mode find` passes.
- `scripts/inspect_serverless_find_e2e.py ... --cold-count 1` passes.
- Repeated warm calls meet average <= 5s and P90 <= 8s.
- Cold start behavior is measured and reported separately.
