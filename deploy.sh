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
step "harvest" python3 nss_harvest.py || true
step "build" python3 nss_build.py || { echo "!! build failed: not deploying"; exit "$worst"; }
step "deploy" npx wrangler@latest deploy || true
exit "$worst"
