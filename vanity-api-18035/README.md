# Vanity API 18035

Independent controller and worker integration for the customer-facing TRON
vanity service on port 18035.

Authoritative specification:

`../docs/VANITY_API_18035_DEVELOPMENT_SPEC_20260712.md`

Hard boundaries:

- never import from, connect to, restart, or modify ports 18030, 18031, or 18032;
- never use `/opt/vanity-address-api` or its databases;
- never use the production RunPod endpoint;
- never persist or log a plaintext private key;
- the controller on 43 is the only authoritative task database;
- the Vast worker may persist only non-sensitive progress and Age ciphertext.

The project is not production-ready until every gate in the authoritative
specification passes.
