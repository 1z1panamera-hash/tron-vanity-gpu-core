# Age Encrypted Find Mode

## Purpose

Production `find` mode must return a matched TRON address and an age-encrypted private key without exposing plaintext key material in the API response.

## Product Input

RunPod Serverless request:

```json
{
  "input": {
    "mode": "find",
    "prefix_after_t": "A",
    "suffix": "CDEFG",
    "age_recipient": "age1...",
    "duration_seconds": 15,
    "max_attempts": 10000000000,
    "start_counter": 0,
    "shard_id": 0,
    "shard_count": 1
  }
}
```

The Python wrapper derives the internal CUDA matcher:

```text
target_address = "T" + prefix_after_t + filler + suffix
prefix_len = 2
suffix_len = 5
```

## Python Wrapper Responsibility

Python remains a thin shell:

- Validate product input.
- Compile CUDA binary only when explicitly allowed in RunPod worker.
- Call CUDA/C++ binary.
- Receive internal hit result from the binary.
- Encrypt the private key with customer `age_recipient`.
- Return only:
  - `matched_address`
  - `encrypted_private_key`

Python must not:

- generate candidate keys,
- do secp256k1 point multiplication,
- do Keccak/Base58Check matching,
- log plaintext private keys,
- return plaintext private keys,
- store customer age identity / decrypt key.

## CUDA/C++ Responsibility

CUDA/C++ must implement the heavy path:

- private key candidate generation,
- secp256k1 point math,
- Keccak-256,
- TRON Base58Check,
- prefix-after-T and suffix match,
- shard/stride schedule,
- hit private scalar reconstruction.

For the Python wrapper contract, the internal CUDA binary may emit a matched private key only through local stdout to the wrapper process. The wrapper must immediately age-encrypt it and omit the plaintext from returned JSON.

## Current Status

Not complete.

- Python wrapper now has gated `mode=find`.
- `ALLOW_GPU_FIND=1` is required before `find` can run.
- The sample payload is `RUNPOD_FIND_SAMPLE_PAYLOAD.json`.
- CUDA/C++ `--find` mode is not implemented yet.
- Final performance target is still unproven.

## Safety Gate

Any RunPod result inspection must fail if response JSON includes:

- `private_key`
- `private_key_hex`
- WIF
- mnemonic
- seed
- token
- secret

`encrypted_private_key` is allowed only because it is age ciphertext.
