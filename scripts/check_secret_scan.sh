#!/usr/bin/env bash
# Proves the secret scan still catches a key. A scan that silently finds nothing
# looks the same as a clean repo, so this plants a freshly generated fake GitHub
# token in a temporary folder (never committed) and fails unless gitleaks reports it.
set -euo pipefail

planted_dir="$(mktemp -d)"
trap 'rm -rf "$planted_dir"' EXIT

# Built without a pipe: `tr < /dev/urandom | head` gets SIGPIPE under pipefail
# and kills the script before the scan runs (see docs/debug-log.md).
alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
random_part=""
for _ in $(seq 36); do
  random_part+="${alphabet:RANDOM % ${#alphabet}:1}"
done
printf 'token = "ghp_%s"\n' "$random_part" > "$planted_dir/config.py"

# By default gitleaks exits 1 both when it finds a leak and when it fails to run,
# so a crash would look like a catch. A found leak gets its own code instead.
leak_found_code=99
scan_status=0
gitleaks dir "$planted_dir" --no-banner --redact --exit-code "$leak_found_code" || scan_status=$?

case "$scan_status" in
  "$leak_found_code")
    echo "OK: gitleaks caught the planted token."
    ;;
  0)
    echo "FAIL: gitleaks ran but missed the planted token, so the scan cannot be trusted." >&2
    exit 1
    ;;
  *)
    echo "FAIL: gitleaks did not run (exit code $scan_status), so nothing was scanned." >&2
    exit 1
    ;;
esac
