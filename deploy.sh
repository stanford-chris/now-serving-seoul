#!/bin/bash
# Harvest the registers, rebuild the site, deploy it.
#
# Worst-exit pattern rather than `set -e`, as in seoul-transit-art/deploy.sh:
# a register that could not be read (exit 2) still lets the others' licences
# reach the page. The build refuses on an empty list, so a total failure
# leaves yesterday's site standing rather than deploying an empty one.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
worst=0
step() {
  local name="$1"; shift
  "$@" || { local rc=$?; echo "!! $name FAILED (exit $rc)"; [ "$rc" -gt "$worst" ] && worst=$rc; return $rc; }
}
# python.org 3.13 by path, never a bare python3: under launchd's PATH that can
# be Homebrew's, which is missing packages (sar-page and london-transit-art
# both failed that way in October 2026).
PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

step "harvest" "$PY" nss_harvest.py || true
# English names for places not yet named: one Fable call per 40 new names,
# cached, so a quiet day costs nothing. A failed batch stays Korean-only and is
# retried tomorrow.
step "names" "$PY" nss_names.py || true
step "build" "$PY" nss_build.py || { echo "!! build failed: not deploying"; exit "$worst"; }
# The daily Bluesky post (since 30 October 2026, his call): only once the site
# that the post links to is up, so a failed deploy posts nothing. A quiet day
# (no new complete licence date) exits 0; a failed map reply exits 1 with the
# card already recorded, so tomorrow does not post it again.
# POSTING=0 holds the post and still deploys the site: his call, 29 October
# 2026, before the first live post, and again on 30 October ("We shouldn't post
# to Bluesky"). Do not set it to 1 without his say-so.
POSTING=0
if step "deploy" /opt/homebrew/bin/npx --yes wrangler@latest deploy; then
  if [ "$POSTING" = 1 ]; then
    step "post" "$PY" nss_post.py || true
  else
    echo "posting held (POSTING=0 in deploy.sh): nothing posted"
  fi
else
  echo "!! deploy failed: not posting"
fi
exit "$worst"
