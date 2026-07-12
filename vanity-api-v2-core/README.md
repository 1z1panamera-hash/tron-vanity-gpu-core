# Vanity API V2 Core

Independent core-adaptation workspace for the new RTX 5090 service.

This directory contains the CUDA core, its single-context scheduler, and the
private worker daemon for the independent port 18035 service. The controller
API is maintained separately in the sibling `vanity-api-18035` directory.

Hard boundaries:

- Do not access or modify production ports `18030`, `18031`, or `18032`.
- Do not access or modify the production RunPod endpoint.
- Vast instances may be used only through the guarded scripts and explicit authorization.
- Round51 remains immutable evidence; V2 changes are additive patches on top of
  the exact Round51 patch stack.

Current milestone:

1. Parse every `T{prefix}*{suffix}` split whose custom length is 6, 7, or 8.
2. Compile patterns into fixed-size target descriptors suitable for CUDA
   constant memory.
3. Prove descriptor matching is equivalent to direct Base58 string matching.
4. Add a separate generic matcher to Round51 without changing the specialized
   foreground suffix-5 path.

Implemented in the Round52 patch:

- all 24 prefix/suffix splits for custom lengths 6, 7, and 8;
- up to 16 generic targets per candidate stream;
- target IDs in hit metadata;
- configurable one-group launches for bounded preemption;
- automatic single-pattern routing from the existing TRON CLI.

Implemented in the Round53 patch and worker daemon:

- reusable specialized P0 target updates without one-shot pinned-memory reuse;
- GPU stream-state export/import inside one CUDA context;
- bounded P0/P1/P2 scheduling with persistent per-class cursors;
- CPU hit verification, locked-memory private-key handling, Age encryption,
  secure clearing, and an encrypted SQLite outbox;
- strict owner-only Unix socket protocol with durable hit ACKs.

The RTX 5090 integration gates passed: scheduler loss 1.93%, P0 takeover P99
13.793ms, all 24 pattern splits correct, and real encrypted-hit delivery passed.
See `docs/CORE_STATUS.md` and `results/rtx5090_round53_20260712/`.

Local checks:

```bash
scripts/local_check.sh
```
