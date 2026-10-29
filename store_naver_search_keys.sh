#!/bin/bash
# Store the Naver Search API keys (Client ID and Client Secret) in the macOS
# Keychain, for nss_blogs.py. Added 29 October 2026, his call, to replace the
# scraped search.naver.com results with Naver's official blog search API.
#
# Run it by typing its name; it prompts with the input hidden, so neither value
# lands in shell history, on screen or in a transcript:
#
#   bash ~/Projects/now-serving-seoul/store_naver_search_keys.sh
#
# It tests the pair with one blog search before saving anything.

set -euo pipefail

SERVICE="naver-search-api"

printf 'Paste the Client ID (input hidden), then press return: '
read -rs ID; printf '\n'
printf 'Paste the Client Secret (input hidden), then press return: '
read -rs SECRET; printf '\n'
ID="$(printf '%s' "$ID" | tr -d '[:space:]')"
SECRET="$(printf '%s' "$SECRET" | tr -d '[:space:]')"
if [ -z "$ID" ] || [ -z "$SECRET" ]; then
  echo "Nothing entered: no change made." >&2
  exit 1
fi

echo "Testing with one blog search..."
CODE="$(curl -s -o /tmp/naver-search-test.json -w '%{http_code}' \
  "https://openapi.naver.com/v1/search/blog.json?query=%EC%84%9C%EC%9A%B8&display=1" \
  -H "X-Naver-Client-Id: $ID" -H "X-Naver-Client-Secret: $SECRET")"
if [ "$CODE" != "200" ]; then
  echo "Naver answered $CODE: $(head -c 300 /tmp/naver-search-test.json)" >&2
  echo "Nothing saved." >&2
  rm -f /tmp/naver-search-test.json
  exit 1
fi
rm -f /tmp/naver-search-test.json

security add-generic-password -U -s "$SERVICE" -a client-id -w "$ID"
security add-generic-password -U -s "$SERVICE" -a client-secret -w "$SECRET"
echo "Saved to the Keychain (service $SERVICE, accounts client-id and client-secret)."
