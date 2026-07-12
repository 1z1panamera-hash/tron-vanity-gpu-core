# 18035 Deployment Boundary

This deployment is independent from the existing 18030, 18031, and 18032
services. It uses only these names and paths:

- `/opt/vanity-api-18035`
- `/etc/vanity-api-18035`
- `/run/vanity-api-18035`
- `vanity-api-18035.service`
- `vanity-gpu-core-18035.service`
- `vanity-gpu-worker-18035.service`

The controller and worker environment examples contain placeholders only. Never
install an example file as production configuration without replacing every
placeholder and setting mode `0600`.

The controller TLS certificate is the public server identity used by both the
customer and worker. The worker client certificate is issued by a separate
private worker CA. The controller requests a client certificate at TLS level and
requires the configured worker ID to equal the certificate common name on every
internal route. Customer routes do not require a client certificate.

The callback dispatcher runs inside the single controller process so that only
one process writes the authoritative SQLite database. Callback I/O is
asynchronous, fixed to the configured HTTPS URL, bounded by a five-second
timeout, and backed by a persistent retry outbox.

Do not enable either service or open TCP 18035 until `deployment_preflight.py`
passes on its target host and the existing service baseline has been recorded.
