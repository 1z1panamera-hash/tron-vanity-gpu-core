# Age Encrypted Find Mode

## Purpose

Production `find` mode must return a matched TRON address and an age-encrypted private key without exposing plaintext key material in the API response.

## Product Input

RunPod Serverless request:

```json
{
  "input": {
    "mode": "find",
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
target_address = "T" + filler + suffix
prefix_len = 0
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
- suffix-only last-5 match over complete Base58Check address,
- shard/stride schedule,
- hit private scalar reconstruction.

For the Python wrapper contract, the internal CUDA binary may emit a matched private key only through local stdout to the wrapper process. The wrapper must immediately age-encrypt it and omit the plaintext from returned JSON.

## Current Status

Locally wired, pending RunPod proof.

- Python wrapper now has gated `mode=find`.
- `ALLOW_GPU_FIND=1` is required before `find` can run.
- The sample payload is `RUNPOD_FIND_SAMPLE_PAYLOAD.json`.
- The original self-written CUDA/C++ `--find` mode emits an internal hit result for the Python wrapper, but remains staging.
- The patched high-speed VanitySearch backend now has `TRON_JSON_HIT_OUTPUT=1` for internal JSON hits.
- `app.py` can route `find` through the VanitySearch backend, parse the internal JSON hit, and age-encrypt before returning.
- Final end-to-end performance target is average <= 5 seconds and P90 <= 8 seconds; cold/warm Serverless timings are still unproven.
- Local response-contract test `tests/verify_find_response_contract.py` uses fake local GPU/VanitySearch/age binaries to verify that matched API responses contain `encrypted_private_key` and omit plaintext key markers.

## CUDA Binary Output Boundary

`src/tron_gpu_core.cu --find` and patched VanitySearch JSON hit mode may include an internal key value in local stdout when a match is found. That stdout is an internal process boundary only:

- It must be consumed by `app.py`.
- It must not be returned directly to RunPod callers.
- It must not be written to controller logs.
- `app.py` must encrypt it with the customer age recipient and return only `encrypted_private_key`.

The internal key value is normalized before encryption. Patched VanitySearch can produce a valid scalar whose hex representation has leading zeroes; if the C++ `GetBase16()` output is shorter than 64 characters, the C++ JSON path and the Python wrapper left-pad it to 64 hex characters. Non-hex values and values longer than 64 characters remain invalid.

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
