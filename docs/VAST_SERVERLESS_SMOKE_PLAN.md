# Vast Serverless Smoke Plan

Purpose: run a low-cost comparison against RunPod Serverless for TRON suffix-only vanity address generation.

This is an experiment, not a migration. The existing RunPod endpoint remains the production GPU path until Vast proves lower latency, stable allocation, and acceptable cost.

## Scope

- Rule: TRON suffix-only last 5 Base58 characters.
- Request route: `POST /find`.
- Health route: `POST /health` or `GET /health`.
- Target image: `ghcr.io/1z1panamera-hash/tron-vanity-gpu-core:vast-serverless-latest`.
- Vast endpoint profile: first test uses scale-to-zero.
- Workergroup max workers: 1 for the first smoke test.
- GPU preference: start with RTX 5090 or RTX PRO 6000 class if available.

## Files

- `Dockerfile.vast-serverless`: Vast-specific image with prebuilt VanitySearch TRON worker.
- `worker.py`: Vast PyWorker route proxy.
- `vast_model_server.py`: local backend that calls the existing `app.handler` contract.
- `vast/start_vast_worker.sh`: starts backend and PyWorker in the same container.
- `requirements-vast.txt`: Vast-only Python dependencies.
- `.github/workflows/build-vast-serverless-image.yml`: builds/pushes the GHCR image.

## Safety Rules

- Do not run GPU work on `47.80.70.211`.
- Do not write customer secrets into Vast templates or repo files.
- Do not log request or response bodies from the Vast backend.
- Return only `matched_address`, `public_key_uncompressed_hex`, `encrypted_private_key`, and non-sensitive timings.
- Use only test age recipients for smoke tests.
- Destroy or stop test resources after measurements.

## First Measurement

1. Build and publish the Vast image with GitHub Actions.
2. Create a private Vast template using the GHCR image.
3. Launch mode should run the Docker entrypoint.
4. Create a Vast Serverless endpoint with:
   - `min_workers = 0`
   - `max_workers = 1`
   - `min_load = 0`
   - `target_util = 0.9`
5. Create a workergroup with one GPU profile.
6. Send one `/health` request.
7. Send one `/find` request with suffix `CDEFG` and a test age recipient.
8. Record:
   - time to first ready worker
   - route delay
   - worker execution time
   - total wall time
   - GPU model
   - whether matched is true
   - whether age ciphertext exists
   - cost delta from Vast billing

## Decision Gate

Continue with Vast only if the first smoke proves:

- stable worker creation,
- no plaintext key material in response or logs,
- successful suffix hit,
- end-to-end latency competitive with RunPod,
- cost is not worse than the current RunPod flow.

If the first worker spends minutes loading or if GHCR image/template compatibility blocks deployment, stop and do not keep burning credits.
