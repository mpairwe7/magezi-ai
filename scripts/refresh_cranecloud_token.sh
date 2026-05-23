#!/usr/bin/env bash
# Refresh the Crane Cloud access token (~/.cranecloud/token).
# Reads credentials from ~/.cranecloud/credentials (JSON: {"email","password"}, mode 600).
# Tokens are valid ~10 days; recommended cron interval: every 5 days.
#
# Cron entry:
#   0 4 */5 * * /home/developer/Mpairwe7/FinalYearProject/Magezi/scripts/refresh_cranecloud_token.sh >> /tmp/cranecloud-refresh.log 2>&1

set -u
CC_DIR="${HOME}/.cranecloud"
CREDS="${CC_DIR}/credentials"
TOKEN="${CC_DIR}/token"
LOG_TAG="$(date -u +%FT%TZ) refresh_token"

if [ ! -s "${CREDS}" ]; then
  echo "${LOG_TAG} ERROR credentials missing: ${CREDS}"
  exit 1
fi

# Login
RESP=$(curl -sS -X POST --max-time 30 \
  -H "Content-Type: application/json" \
  --data-binary @"${CREDS}" \
  https://api.cranecloud.io/users/login)

NEW_TOKEN=$(echo "${RESP}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d.get('status') == 'success' and d.get('data', {}).get('access_token'):
        print(d['data']['access_token'])
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
")

if [ -z "${NEW_TOKEN}" ]; then
  echo "${LOG_TAG} ERROR login failed: ${RESP:0:200}"
  exit 1
fi

# Verify before swap
TMP="${TOKEN}.new"
printf "%s" "${NEW_TOKEN}" > "${TMP}"
chmod 600 "${TMP}"

USER_ID="a1b81625-d984-4856-a3a3-9b225f021a94"
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
  -H "Authorization: Bearer ${NEW_TOKEN}" \
  "https://api.cranecloud.io/users/${USER_ID}/projects")

if [ "${CODE}" != "200" ]; then
  echo "${LOG_TAG} ERROR token verify failed: status=${CODE}"
  rm -f "${TMP}"
  exit 1
fi

# Decode expiry from JWT
EXP=$(python3 -c "
import base64, json
tok = open('${TMP}').read().strip()
payload = tok.split('.')[1]
payload += '=' * (-len(payload) % 4)
print(json.loads(base64.urlsafe_b64decode(payload))['exp'])
")

mv -f "${TMP}" "${TOKEN}"
echo "${LOG_TAG} OK token refreshed, expires=$(date -u -d @${EXP} +%FT%TZ) (epoch ${EXP})"
