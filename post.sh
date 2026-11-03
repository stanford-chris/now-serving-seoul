#!/bin/bash
# The daily Bluesky post, 08:00 Seoul (launchd com.chrisstanford.nowservingseoul-post).
#
# Split from deploy.sh on 3 November 2026, his call: the post goes up at
# the morning commute, not at 06:20 with the site. It posts only once
# deploy.sh has recorded TODAY's deploy in data/deployed, so the card never
# links to a site that lacks its day. A deploy still running (a slow harvest)
# is waited for, up to 45 minutes: next_day() only moves forward, so a day
# skipped here is never posted.
#
# A quiet day (no new complete licence date) exits 0; a failed map reply
# exits 1 with the card already recorded, so tomorrow does not post it again.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

# POSTING=0 holds the post. Held from 29 October 2026 (his call) and released
# on 3 November ("We can start posting"); set it back to 0 to hold again.
POSTING=1
if [ "$POSTING" != 1 ]; then
  echo "$(date '+%F %T') posting held (POSTING=0 in post.sh): nothing posted"
  exit 0
fi

today=$(TZ=Asia/Seoul date +%F)
for _ in $(seq 1 45); do
  [ "$(cat data/deployed 2>/dev/null)" = "$today" ] && break
  pgrep -f "now-serving-seoul/deploy.sh" >/dev/null || break
  sleep 60
done
if [ "$(cat data/deployed 2>/dev/null)" != "$today" ]; then
  echo "$(date '+%F %T') !! no deploy recorded for $today: not posting"
  exit 1
fi
echo "$(date '+%F %T') posting"
exec "$PY" nss_post.py
