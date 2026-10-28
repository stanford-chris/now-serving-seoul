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
# The weekly blog pass ("opened", and a post's own English name), Mondays only.
if [ "$(TZ=Asia/Seoul date +%u)" = 1 ]; then
  step "blogs" "$PY" nss_blogs.py || true
fi
step "build" "$PY" nss_build.py || { echo "!! build failed: not deploying"; exit "$worst"; }
step "deploy" /opt/homebrew/bin/npx --yes wrangler@latest deploy || true
exit "$worst"
