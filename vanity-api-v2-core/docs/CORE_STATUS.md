# V2 Core Status

Date: 2026-07-12

## Boundary

- This directory owns only the independent CUDA core and its worker daemon.
- The controller API lives in the sibling `vanity-api-18035` directory.
- No production service, endpoint, port, image, or production host was changed.
- Round51 remains immutable; V2 is a replayable additive patch.

## Completed Offline

- Exact Round51 source identity is enforced with per-file SHA-256 checks.
- `T*{suffix5}` remains on the original specialized Round51 path.
- All `T{prefix}*{suffix}` splits with custom length 6, 7, or 8 are parsed.
- All 24 length splits are represented by a fixed 136-byte CUDA descriptor.
- Generic matching supports up to 16 active targets in constant memory.
- Keccak and checksum work is shared before target matching.
- A single `58^8` residue supports suffix lengths 1 through 8.
- Hit metadata carries the matching target ID and endomorphism ID.
- The existing CLI routes one generic pattern or multiple input patterns to V2.
- CLI hit handling verifies the address against the selected pattern on CPU.
- One-group launches allow bounded foreground takeover without rebuilding CUDA state.
- The patch replays cleanly on a pristine Round51 source tree.
- CPU reference, descriptor, device-equivalent, residue, metadata, and invalid-input tests pass.

## Completed Worker Core

- Round53 adds public GPU key-state export/import without rebuilding the CUDA context.
- One daemon owns one CUDA context and schedules P0, P1, and P2 streams.
- P0 rotates up to 8 foreground targets one per GPU group; P1/P2 support up to 16 targets.
- Stream state and CPU scalar cursors are separate and survive class switching.
- GPU hits are reconstructed and verified on CPU before delivery.
- Private key bytes stay in locked memory, are passed to Age through an anonymous pipe,
  and are cleared on success and error paths.
- Only armored Age ciphertext is durably stored; plaintext is rejected by the outbox.
- The encrypted result is committed before socket notification and requires an ACK.
- The private Unix socket, worker database, and parent directories enforce owner-only modes.
- The P0 reusable-target path no longer calls the one-shot pinned-memory `SetPattern` path.

## Completed on RTX 5090

- Round52 compiled for CUDA `sm_120` and linked successfully.
- Generic V2 hash kernels use 85 registers, 96 bytes of stack, and zero spills.
- Specialized Round51 hash kernels use 79 registers, 96 bytes of stack, and zero spills.
- GPU forced-hit correctness passed for all 24 prefix/suffix split vectors.
- Correct target isolation passed for 1, 4, 8, and 16 simultaneous targets.
- Specialized suffix-5 measured about 3.69-3.77B/s steady, with a 4.03B/s peak sample.
- Representative prefix-gated generic modes measured about 5.3-5.5B/s.
- Representative generic suffix-only mode measured about 3.6-3.77B/s.
- Same-host Round51/Round52 comparison found no measurable regression on the
  preserved specialized Round51 path.
- Multi-target representative throughput measured 5.357687B/s for one target
  and 5.067723B/s for 16 targets.
- One-group takeover measured 13.479ms P50 and 13.515ms P99.

Round53 integration validation on a Secure Cloud RTX 5090 with driver 580.95.05:

- Current build uses 168 registers, 33072 bytes cumulative stack, and zero spills.
- Real suffix-5 daemon hit completed in 440.037ms and passed CPU address verification.
- Age ciphertext was committed before notification; ACK stopped resend; modes were `0600`.
- Continuous scheduler baseline measured 4.688677B/s and scheduled operation 4.598225B/s.
- Scheduler overhead was 1.929159%, below the 3% acceptance limit.
- Active-background-to-P0 takeover measured 13.699ms P50 and 13.793ms P99.
- P2 to P1 to P2 switching preserved the P2 cursor (44032 to 100352).
- The current Round53 build passed all 24 forced-hit prefix/suffix splits and 1/4/8/16 targets.
- Current multi-target throughput measured 5.045238B/s for one target and
  4.782762B/s for 16 targets.

Round52 evidence is under `results/rtx5090_20260712/`. Round53 worker and
scheduler evidence is under `results/rtx5090_round53_20260712/`.

## Remaining Integration Gates

1. Complete controller-to-worker mTLS deployment and restart recovery tests.
2. Complete real callback allowlist, timeout, retry, and idempotency validation.
3. Run the combined controller/worker end-to-end acceptance suite on the deployment hosts.
4. Deploy only after configuration review; production ports 18030, 18031, and 18032
   must remain untouched.
