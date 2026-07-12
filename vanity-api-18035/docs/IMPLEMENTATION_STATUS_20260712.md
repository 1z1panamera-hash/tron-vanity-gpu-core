# Vanity API 18035 Implementation Status

Date: 2026-07-12

## Completed

- Independent controller database, `/v1/find`, P0 singleflight/cache/timeout,
  P1/P2 persistent queue, lease protocol, and callback outbox.
- Fixed customer IP allowlist and fixed callback URL; no customer API token.
- TLS customer endpoint and mTLS worker routes with source-IP, timestamp, nonce,
  configured worker ID, and client-certificate CN enforcement.
- One-CUDA-context RTX 5090 daemon with P0/P1/P2 stream switching.
- CPU hit verification, locked-memory private-key handling, Age encryption,
  memory clearing, encrypted durable worker outbox, and result ACK protocol.
- Real RTX 5090 acceptance: all 24 six/eight-position split vectors, 1/4/8/16
  targets, 1.929% scheduler overhead, 13.793ms P0 takeover P99, and a real
  encrypted P0 hit.
- Local controller/worker acceptance: 42 tests, including 100 identical P0
  requests sharing one task, disconnect/retry, timeout reset, queue refill,
  callback recovery, real TLS handshakes, mTLS rejection cases, and end-to-end
  controller/worker delivery.
- Controller code and dependencies installed on 43 under
  `/opt/vanity-api-18035`; its unit is disabled and inactive.

## Current Safety State

- TCP 18035 is not listening and the AWS firewall has not been opened.
- `/etc/vanity-api-18035/controller.env` does not exist; no placeholder service
  can start accidentally.
- Existing services remain active. The 18030 and 18031 health endpoints return
  HTTP 200 after the isolated install.
- No Vast instance remains active from core validation.
- No customer value, API key, Age identity, TLS private key, or plaintext TRON
  private key is stored in this repository.

## Published Worker Artifact

- Git branch: `vanity-api-18035`
- Source commit: `125893c1b633b84bf7cd3fb1db272d2cff6bbd59`
- Image tag: `ghcr.io/1z1panamera-hash/tron-vanity-gpu-core:vanity18035-worker-125893c1b633b84bf7cd3fb1db272d2cff6bbd59`
- OCI digest: `sha256:3db9f27b50ee3c0670898fbb6862fc097a3e92c3fd8afa285d853988397a0619`
- GitHub Actions run: `29204099843` (`success`)

Production deployment must pin the digest, not the mutable `latest` tag.

The current Secure Cloud/static-IP RTX 5090 shortlist is recorded in
`VAST_FIXED_HOST_SHORTLIST_20260712.md`. It was read-only; no host was rented.

## Required Before Activation

1. Customer fixed IPv4.
2. Customer fixed HTTPS callback URL and confirmation that it allows the 43
   static IPv4.
3. Customer Age recipient public key. The Age identity remains with the customer.
4. Controller TLS certificate/key and the separate worker mTLS CA/client pair.
5. A fixed Vast Secure Cloud RTX 5090 host with driver 580 or newer and a fixed
   outbound IPv4.
6. Pull the pinned worker image on the fixed host, mount worker configuration,
   then run the full real-host end-to-end and restart/outage recovery tests.
7. User approval before enabling the controller or opening AWS TCP 18035.
