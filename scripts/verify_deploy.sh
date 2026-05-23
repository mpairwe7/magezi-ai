#!/usr/bin/env bash
# Post-deploy verification: probe a Magezi instance (local container or
# Crane Cloud URL), run smoke suites against it, print summary.
# Usage:  ./scripts/verify_deploy.sh <base_url>
#   e.g.: ./scripts/verify_deploy.sh http://127.0.0.1:8088
#         ./scripts/verify_deploy.sh https://magezi-ai-XXXX.renu-01.cranecloud.io

set -u
BASE="${1:?usage: verify_deploy.sh <base_url>}"

cd "$(dirname "$0")/.."

echo "== Verifying $BASE =="
echo
echo "--- /health ---"
curl -s -m 10 "$BASE/health" | python3 -m json.tool 2>&1 || true
echo
echo "--- /docs head ---"
curl -s -m 10 -o /dev/null -w "HTTP %{http_code} type=%{content_type}\n" "$BASE/docs"
echo
echo "--- frontend root ---"
curl -s -m 10 -o /tmp/magezi_bench/_root.html -w "HTTP %{http_code} size=%{size_download} ttfb=%{time_starttransfer}s\n" "$BASE/"
echo "title in HTML: $(grep -o '<title>[^<]*' /tmp/magezi_bench/_root.html | head -1)"
echo
echo "--- backend smoke ---"
python3 scripts/smoke_api.py --base "$BASE" 2>&1 | tail -20
echo
echo "--- frontend-API integration smoke ---"
python3 scripts/smoke_frontend_api.py --base "$BASE" 2>&1 | tail -16
