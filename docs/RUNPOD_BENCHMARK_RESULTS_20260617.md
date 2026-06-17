# RunPod Benchmark Results 2026-06-17

## Scope

This records the first RunPod Serverless tests for the TRON vanity GPU core.

No benchmark or GPU workload was run on `47.80.70.211`.
No private key, seed, mnemonic, token, or secret was output.

## Validate Endpoint

- Endpoint name: `tron-vanity-gpu-core`
- Request id: `a1441059-abc4-4aa9-9f21-30a03d30e934-u1`
- Result: CUDA compile passed and vector validation passed
- Vectors: 4 total, 4 passed, 0 failed

## A100 80GB Benchmark

- Endpoint id: `vf96wl4boinmqv`
- Request id: `84ffd3c6-f70e-4f82-b875-1640fe76c06f-u1`
- GPU: `NVIDIA A100-SXM4-80GB`
- Kernel mode: `incremental_public_key_walk`
- Duration setting: 10 seconds
- Attempts: 1,048,576
- Addresses per second: 33,098.886491
- Keys per second: 33,098.886491
- Matched: false

## Blackwell 96GB Benchmark

- Endpoint id: `mf8hnwrsf293e1`
- Request id: `d9ad6ab4-7567-4205-a11e-3d00029ada90-u1`
- GPU: `NVIDIA RTX PRO 6000 Blackwell Server Edition`
- Kernel mode: `incremental_public_key_walk`
- Duration setting: 10 seconds
- Attempts: 2,097,152
- Addresses per second: 112,930.931302
- Keys per second: 112,930.931302
- Matched: false
- RunPod delay: 3.31s
- RunPod execution time: 30.47s

## Conclusion

The current CUDA core is useful as a correctness and integration smoke test, but it is not a production-speed vanity generator.

The measured speed is far below the target needed for default matching rule `prefix_len=2`, `suffix_len=5` over the full TRON Base58 address. Because TRON's leading `T` is fixed, the effective random target is 1 variable prefix character after `T` plus 5 suffix characters, or about `58^6` candidates. The current implementation should not be used to estimate production cost or worker count.

The likely bottleneck is the custom full address-generation path, especially secp256k1 field arithmetic and point walking implementation. Further RunPod spending on this exact core is not recommended until the core is replaced or substantially rewritten against a mature, verifiable GPU vanity-generation approach.

## Next Direction

- Keep this implementation only as a test-vector and RunPod handler scaffold.
- Do not treat its throughput as real GPU capability.
- Compare against a mature audited CUDA/OpenCL vanity-generation core, or rewrite the core with a performance-first design.
- Preserve the project security boundary: production hits must use `age` encryption for private key return, and the controller must not save plaintext private keys.
