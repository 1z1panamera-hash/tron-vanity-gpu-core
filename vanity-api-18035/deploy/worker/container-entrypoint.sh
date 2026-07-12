#!/usr/bin/env bash
set -euo pipefail
umask 077

required=(
  VANITY18035_WORKER_ID
  VANITY18035_CONTROLLER_URL
  VANITY18035_AGE_RECIPIENT
  VANITY18035_CONTROLLER_CA
  VANITY18035_WORKER_CERT
  VANITY18035_WORKER_KEY
)
for name in "${required[@]}"; do
  if [ -z "${!name:-}" ]; then
    echo "missing required 18035 worker configuration: $name" >&2
    exit 2
  fi
done

if [[ "$VANITY18035_AGE_RECIPIENT" != age1* ]]; then
  echo "invalid Age recipient" >&2
  exit 2
fi
for path in \
  "$VANITY18035_CONTROLLER_CA" \
  "$VANITY18035_WORKER_CERT" \
  "$VANITY18035_WORKER_KEY"; do
  if [ ! -f "$path" ]; then
    echo "required TLS file is unavailable" >&2
    exit 2
  fi
done
if [ $((8#$(stat -c '%a' "$VANITY18035_WORKER_KEY") & 8#077)) -ne 0 ]; then
  echo "worker TLS private key must have mode 0600 or stricter" >&2
  exit 2
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA runtime is unavailable" >&2
  exit 3
fi
gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
if [[ "$gpu_name" != *"RTX 5090"* ]]; then
  echo "worker requires an RTX 5090" >&2
  exit 3
fi
driver_major="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1 | cut -d. -f1)"
if [ "${driver_major:-0}" -lt 580 ]; then
  echo "worker requires NVIDIA driver 580 or newer" >&2
  exit 3
fi

install -d -o 10001 -g 10001 -m 0700 \
  /run/vanity-api-18035 \
  /run/vanity-api-18035/tls \
  /opt/vanity-api-18035/data \
  /opt/vanity-api-18035/logs
install -o 10001 -g 10001 -m 0644 \
  "$VANITY18035_CONTROLLER_CA" /run/vanity-api-18035/tls/controller-ca.crt
install -o 10001 -g 10001 -m 0644 \
  "$VANITY18035_WORKER_CERT" /run/vanity-api-18035/tls/worker.crt
install -o 10001 -g 10001 -m 0600 \
  "$VANITY18035_WORKER_KEY" /run/vanity-api-18035/tls/worker.key
printf '%s\n' "$VANITY18035_AGE_RECIPIENT" > /run/vanity-api-18035/age-recipient.txt
chmod 0600 /run/vanity-api-18035/age-recipient.txt
chown 10001:10001 /run/vanity-api-18035/age-recipient.txt

export VANITY18035_ENV=production
export VANITY18035_WORKER_DB=/opt/vanity-api-18035/data/worker.sqlite3
export VANITY18035_CORE_SOCKET=/run/vanity-api-18035/core.sock
export VANITY18035_ALLOW_INSECURE_LOCAL=false
export VANITY18035_CONTROLLER_CA=/run/vanity-api-18035/tls/controller-ca.crt
export VANITY18035_WORKER_CERT=/run/vanity-api-18035/tls/worker.crt
export VANITY18035_WORKER_KEY=/run/vanity-api-18035/tls/worker.key

python3 -c 'from vanity18035.worker_config import WorkerSettings; WorkerSettings.from_env().validate()'

exec /usr/bin/setpriv --reuid=10001 --regid=10001 --init-groups \
  /usr/bin/supervisord -n -c /etc/vanity-api-18035/supervisord.conf
