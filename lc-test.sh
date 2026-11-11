#!/usr/bin/env bash
# Reproduce the LC stage article blob upload flow. Requires curl and jq.
set -uo pipefail

BASE="${LC_BASE_URL:-https://stage-table.novasplit.ai}"
BASE="${BASE%/}"
for command in curl jq; do
  command -v "$command" >/dev/null || { printf 'Missing command: %s\n' "$command" >&2; exit 1; }
done

read -rp 'LC username: ' LC_USER
read -rsp 'LC password: ' LC_PASSWORD
printf '\n'
TOKEN=$(jq -n --arg user "$LC_USER" --arg password "$LC_PASSWORD" \
  '{user_name: $user, password: $password}' |
  curl -fsS --max-time 15 "$BASE/api/v1/login/password" \
    -H 'Content-Type: application/json' --data-binary @- |
  jq -er '.access_token') || { unset LC_PASSWORD; echo 'Login failed.' >&2; exit 1; }
unset LC_PASSWORD

WORKSPACE_ID=$(jq -n --arg name "seo-blob-test-$(date +%s)" '{workspace_name: $name}' |
  curl -fsS --max-time 15 "$BASE/api/v1/workspaces" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data-binary @- |
  jq -er '.workspace_id') || { echo 'Workspace creation failed.' >&2; exit 1; }
printf 'Test workspace: %s\n' "$WORKSPACE_ID"

cleanup_prompt() {
  local answer
  printf '\nDelete test workspace %s? [y/N] ' "$WORKSPACE_ID"
  read -r answer || answer=''
  if [[ "$answer" == [yY] || "$answer" == [yY][eE][sS] ]]; then
    curl -fsS --max-time 15 -X DELETE -H "Authorization: Bearer $TOKEN" \
      "$BASE/api/v1/workspaces/$WORKSPACE_ID" >/dev/null && echo 'Test workspace deleted.' ||
      echo 'Cleanup failed; delete the test workspace manually.' >&2
  else
    echo 'Test workspace retained for inspection.'
  fi
}
trap cleanup_prompt EXIT

TABLE=$(jq -n --arg ws "$WORKSPACE_ID" '{workspace_id: $ws, table_name: "articles"}' |
  curl -fsS --max-time 15 "$BASE/api/v1/tables" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data-binary @-) || exit 1
TABLE_ID=$(jq -er '.table_id' <<< "$TABLE") || exit 1
TITLE_COL=$(jq -er '.columns[] | select(.name == "Title") | .column_id' <<< "$TABLE") || exit 1
DOC_COL=$(jq -er '.columns[] | select(.name == "Doc") | .column_id' <<< "$TABLE") || exit 1
printf 'Table: %s; Doc column: %s\n' "$TABLE_ID" "$DOC_COL"

for n in 1 2 3; do
  ROW_ID=$(jq -n --arg col "$TITLE_COL" --arg title "blob-test-$n" '{row_data: {($col): $title}}' |
    curl -fsS --max-time 15 "$BASE/api/v1/tables/$TABLE_ID/rows" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data-binary @- |
    jq -er '.row_id') || exit 1
  URL="$BASE/api/v1/tables/$TABLE_ID/rows/$ROW_ID/blob/$DOC_COL"
  printf '\nUploading row %s\n' "$ROW_ID"
  printf '# blob-test-%s\n\nSmall markdown file.\n' "$n" |
    curl -fsS --max-time 15 -o /dev/null -w 'HTTP %{http_code}, elapsed %{time_total}s\n' \
      -X PUT -H "Authorization: Bearer $TOKEN" \
      -F "file=@-;filename=blob-test-$n.md;type=text/markdown" "$URL"
  status=$?
  if (( status != 0 )); then
    printf 'Upload failed: curl exit %s. Attempting readback for row %s:\n' "$status" "$ROW_ID"
    curl -sS --max-time 15 -w '\nHTTP %{http_code}, elapsed %{time_total}s\n' \
      -H "Authorization: Bearer $TOKEN" "$URL" || true
    exit "$status"
  fi
done
echo 'All three uploads succeeded; the intermittent timeout did not reproduce.'
