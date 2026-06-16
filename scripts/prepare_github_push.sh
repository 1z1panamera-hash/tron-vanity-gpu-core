#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
    cat >&2 <<'USAGE'
Usage:
  scripts/prepare_github_push.sh --repo-url https://github.com/OWNER/tron-vanity-gpu-core.git
  scripts/prepare_github_push.sh --repo-url https://github.com/OWNER/tron-vanity-gpu-core.git --push

Default mode does not push. It only audits the repository and shows the exact
commands that would be used.

Use --push only after the GitHub repository exists and the user has explicitly
confirmed uploading this code to GitHub.
USAGE
}

repo_url=""
do_push=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo-url)
            [ "$#" -ge 2 ] || { usage; exit 2; }
            repo_url="$2"
            shift 2
            ;;
        --push)
            do_push=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

if [ -z "$repo_url" ]; then
    usage
    exit 2
fi

case "$repo_url" in
    https://github.com/*/*.git|git@github.com:*/*.git)
        ;;
    *)
        echo "repo URL must be a GitHub .git URL" >&2
        exit 2
        ;;
esac

echo "== public repository audit"
python3 scripts/public_repo_audit.py >/tmp/tron_gpu_public_repo_audit.json
cat /tmp/tron_gpu_public_repo_audit.json

echo "== local preflight"
scripts/local_preflight.sh >/tmp/tron_gpu_local_preflight.log
tail -n 5 /tmp/tron_gpu_local_preflight.log

echo "== current commit"
git rev-parse HEAD

echo "== remote plan"
if git remote get-url origin >/dev/null 2>&1; then
    current_origin="$(git remote get-url origin)"
    if [ "$current_origin" != "$repo_url" ]; then
        echo "origin exists and differs: $current_origin" >&2
        echo "Refusing to overwrite origin automatically." >&2
        exit 1
    fi
    echo "origin already set to $repo_url"
else
    echo "would run: git remote add origin $repo_url"
fi

echo "would run: git push -u origin main"

if [ "$do_push" -ne 1 ]; then
    echo "dry_run_only=true"
    exit 0
fi

echo "== pushing to GitHub"
if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "$repo_url"
fi
git push -u origin main
