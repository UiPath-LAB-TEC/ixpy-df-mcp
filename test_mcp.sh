#!/usr/bin/env bash
set -euo pipefail

MCP_URL="${MCP_URL:-}"
TOKEN="${UIPATH_ACCESS_TOKEN:?Set UIPATH_ACCESS_TOKEN first}"
BATCH_ID="${1:-59902d56-b6ae-4622-ac16-1cb8a646c096}"
ENTITY_KEY="${2:-${UIPATH_EXTRACTION_ENTITY_KEY:-}}"
MAX_RESULTS="${3:-}"
MAX_RESPONSE_BYTES="${4:-}"

extract_json() {
  local raw="$1"
  if printf '%s' "$raw" | jq -e . >/dev/null 2>&1; then
    printf '%s' "$raw"
  else
    printf '%s\n' "$raw" | tr -d '\r' | sed -n 's/^data: //p' | tail -n1
  fi
}

post_mcp() {
  local body="$1"
  curl -sS -X POST "$MCP_URL" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "mcp-session-id: ${SESSION_ID:-}" \
    -H "mcp-protocol-version: ${PROTO:-}" \
    --data "$body"
}

# 1) initialize (captures mcp-session-id header)
HDR_FILE="$(mktemp)"
INIT_RAW=$(curl -sS -D "$HDR_FILE" -X POST "$MCP_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}')

SESSION_ID=$(awk 'tolower($1)=="mcp-session-id:"{print $2}' "$HDR_FILE" | tr -d '\r')
INIT_JSON=$(extract_json "$INIT_RAW")
PROTO=$(printf '%s\n' "$INIT_JSON" | jq -r '.result.protocolVersion')

echo "SESSION_ID=$SESSION_ID"
echo "PROTO=$PROTO"

# 2) send initialized notification
post_mcp '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' >/dev/null

# 3) list tools
TOOLS_RAW=$(post_mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
TOOLS_JSON=$(extract_json "$TOOLS_RAW")
echo "TOOLS:"
printf '%s\n' "$TOOLS_JSON" | jq .

SUPPORTS_MAX_RESULTS=$(printf '%s\n' "$TOOLS_JSON" | jq -r '
  (.result.tools[]? | select(.name=="query_extraction_results")
   | (.inputSchema.properties | has("maxResults"))) // false
')
SUPPORTS_MAX_RESPONSE_BYTES=$(printf '%s\n' "$TOOLS_JSON" | jq -r '
  (.result.tools[]? | select(.name=="query_extraction_results")
   | (.inputSchema.properties | has("maxResponseBytes"))) // false
')

if [[ -n "$MAX_RESULTS" && "$SUPPORTS_MAX_RESULTS" != "true" ]]; then
  echo "WARN: Deployment does not expose maxResults yet; ignoring arg 3"
fi
if [[ -n "$MAX_RESPONSE_BYTES" && "$SUPPORTS_MAX_RESPONSE_BYTES" != "true" ]]; then
  echo "WARN: Deployment does not expose maxResponseBytes yet; ignoring arg 4"
fi

# 4) call your tool
CALL_BODY=$(jq -cn --arg b "$BATCH_ID" --arg e "$ENTITY_KEY" --arg mr "$MAX_RESULTS" --arg mrb "$MAX_RESPONSE_BYTES" --argjson sm "$SUPPORTS_MAX_RESULTS" --argjson sb "$SUPPORTS_MAX_RESPONSE_BYTES" \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"query_extraction_results","arguments":(
    {"batchId":$b}
    + (if ($e | length) > 0 then {"entityKey":$e} else {} end)
    + (if $sm and (($mr | length) > 0) then {"maxResults":($mr | tonumber)} else {} end)
    + (if $sb and (($mrb | length) > 0) then {"maxResponseBytes":($mrb | tonumber)} else {} end)
  )}}')
CALL_RAW=$(post_mcp "$CALL_BODY")
CALL_JSON=$(extract_json "$CALL_RAW")
echo "EXTRACTION CALL RESULT:"
printf '%s\n' "$CALL_JSON" | jq .
