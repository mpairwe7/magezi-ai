#!/usr/bin/env bash
# Periodic /health ping for Magezi + Musawo Crane Cloud apps.
# Detects stuck/dead pods and auto-restarts via the Crane Cloud API.
# Wire into crontab: */10 * * * * /home/developer/Mpairwe7/FinalYearProject/Magezi/scripts/keep_alive.sh >> /tmp/magezi-keepalive.log 2>&1

set -u
TOKEN_FILE="${HOME}/.cranecloud/token"
LOG_TAG="$(date -u +%FT%TZ) keep_alive"

ping_app () {
  local name="$1" url="$2" app_id="$3"
  local code
  # First try a 15s probe — backend should always respond fast on a healthy pod.
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${url}/health" || echo "000")
  if [ "${code}" = "200" ]; then
    echo "${LOG_TAG} ${name} OK"
    return 0
  fi

  echo "${LOG_TAG} ${name} UNHEALTHY status=${code} url=${url}"

  # Retry once after 10s before restarting (transient blip).
  sleep 10
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${url}/health" || echo "000")
  if [ "${code}" = "200" ]; then
    echo "${LOG_TAG} ${name} RECOVERED on retry"
    return 0
  fi

  if [ ! -s "${TOKEN_FILE}" ]; then
    echo "${LOG_TAG} ${name} cannot restart — token file empty (${TOKEN_FILE})"
    return 1
  fi

  echo "${LOG_TAG} ${name} RESTARTING via Crane Cloud API"
  local resp
  resp=$(curl -sS -X POST --max-time 30 \
    -H "Authorization: Bearer $(cat "${TOKEN_FILE}")" \
    "https://api.cranecloud.io/apps/${app_id}/restart" || echo '{"status":"error"}')
  echo "${LOG_TAG} ${name} restart_response=${resp}"
}

ping_app "magezi" \
  "https://magezi-ai-c53f499a.renu-01.cranecloud.io" \
  "fef97411-c719-4465-b0f5-01d4fe56bd5e"

ping_app "musawo" \
  "https://musawo-ai-ce243528.renu-01.cranecloud.io" \
  "d36c0871-fa6b-4475-b431-ec8bc6a72996"

ping_app "hustle-coach" \
  "https://hustle-coach-7904cdf3.renu-01.cranecloud.io" \
  "8853cf6e-d8b5-4cab-ab32-05859aa7bc1d"
