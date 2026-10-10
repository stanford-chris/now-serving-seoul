#!/usr/bin/env python3
"""Read the seven districts' food-licence registers and update data/licences.json.

    python3 nss_harvest.py              # read, update, geocode new places
    python3 nss_harvest.py --dry-run    # read and report, write nothing

Each licence is kept by its management number (MGTNO) from the day it is first
seen, with what the register said, why it is or is not listed, and where Kakao
places its road address. A licence that later closes is marked closed with the
register's closing date; nothing is ever deleted.

Exit 0 all read, 1 a lookup or table gap worth a look, 2 a register NOT CHECKED.

⚠️ The API's paging is UNSTABLE: rows are unsorted and each full read repeats
some and skips others (three reads of Yongsan's restaurant list on 10 October
2026 gave 14,330, 14,212 and 13,876 distinct licences of 16,666). Reads are
unioned until the count reaches the list total, or three in a row add nothing.
Copied from ~/Scripts/seoul_weekly.py's licence_rows(), deliberately not
imported across repositories.

⚠️ A register that cannot be read, reads short of the last good count by more
than LIST_SHRINK, or names another district in its addresses is NOT CHECKED:
its licences are neither added nor marked closed. A failed read must never look
like a quiet day, and a short one must never close a licence it merely missed.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

from nss_common import (API, DATA, DISTRICTS, GEOCODE_CACHE, KAKAO_ADDRESS,
                        KAKAO_KEYCHAIN, KEYCHAIN, REGISTERS, STATE, TYPES,
                        english_name, exclusion, lookup_address, neighborhood, reexclude,
                        services, type_info)

SEOUL = ZoneInfo("Asia/Seoul")
FIRST_RUN_DAYS = 70   # how far back an empty state starts the archive
LATE_DAYS = 60        # a licence can enter the register late; look this far back
LIST_SHRINK = 0.98    # a list under 98% of its last good total is a bad read
OTHER_DISTRICT_MAX = 0.01
KAKAO_SPACING = 0.25


def keychain(service, account):
    return subprocess.run(["security", "find-generic-password", "-s", service,
                           "-a", account, "-w"], capture_output=True,
                          text=True).stdout.strip()


def read_once(svc, key):
    rows, a = [], 1
    while True:
        r = subprocess.run(["curl", "-s", "--max-time", "60",
                            API.format(key=key, svc=svc, a=a, b=a + 999)],
                           capture_output=True, text=True, timeout=90,
                           stdin=subprocess.DEVNULL)
        d = json.loads(r.stdout).get(svc)
        if not d or d.get("RESULT", {}).get("CODE") != "INFO-000":
            raise RuntimeError(f"{svc}: {r.stdout[:150]}")
        rows += d.get("row") or []
        total = d["list_total_count"]
        a += 1000
        if a > total:
            return rows, total


def read_all(svc, key, max_reads=12):
    seen, quiet = {}, 0
    for _ in range(max_reads):
        rows, total = read_once(svc, key)
        before = len(seen)
        for r in rows:
            seen.setdefault(r["MGTNO"], r)
        quiet = quiet + 1 if len(seen) == before else 0
        if len(seen) >= total or quiet >= 3:
            return list(seen.values()), total
    raise RuntimeError(f"{svc}: still incomplete after {max_reads} reads "
                       f"({len(seen)} of {total})")


def clean(v):
    return (v or "").strip() if isinstance(v, str) else v


def record(row, district, register, today):
    type_ko = clean(row.get("UPTAENM"))
    type_en, group = type_info(type_ko, register)
    road, lot = clean(row.get("RDNWHLADDR")), clean(row.get("SITEWHLADDR"))
    name = clean(row.get("BPLCNM"))
    return {
        "name": name, "name_en": english_name(name),
        "district": district, "register": register,
        "type_ko": type_ko, "type_en": type_en, "group": group,
        "licensed": clean(row.get("APVPERMYMD")),
        "road": road, "lot": lot, "dong": neighborhood(road, lot),
        "excluded": exclusion(row),
        "status": "licensed", "first_seen": today,
    }


def check_list(rows, last_total, gu):
    """Why a register's read cannot be trusted, or None. Pure, for tests."""
    if last_total and len(rows) < last_total * LIST_SHRINK:
        return f"read {len(rows)}, last good {last_total}"
    other = sum(gu not in (r.get("RDNWHLADDR") or "") + (r.get("SITEWHLADDR") or "")
                for r in rows)
    if other > len(rows) * OTHER_DISTRICT_MAX:
        return f"{other} of {len(rows)} rows are not in {gu}"
    return None


def merge(licences, rows, district, register, today, floor):
    """Add licences dated on or after `floor` not yet tracked, and close the
    tracked ones the register now shows closed. Returns (added, closed,
    unknown types). Only ever called on a read check_list() passed."""
    added = closed = 0
    unknown = set()
    for r in rows:
        mgt = r["MGTNO"]
        operating = r.get("TRDSTATEGBN") == "01"
        if mgt in licences:
            e = licences[mgt]
            if not operating and e["status"] != "closed":
                e["status"], e["closed"] = "closed", clean(r.get("DCBYMD")) or today
                closed += 1
            continue
        day = clean(r.get("APVPERMYMD"))
        if not operating or not day or day < floor:
            continue
        e = record(r, district, register, today)
        if e["type_ko"] not in TYPES and not e["excluded"]:
            unknown.add(e["type_ko"])
        licences[mgt] = e
        added += 1
    return added, closed, unknown


def kakao_lookup(query, key):
    url = KAKAO_ADDRESS + "?" + urllib.parse.urlencode({"query": query})
    r = subprocess.run(["curl", "-s", "-m", "20", "-w", "\n%{http_code}",
                        "-H", f"Authorization: KakaoAK {key}", url],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    body, _, code = r.stdout.rpartition("\n")
    if r.returncode or code != "200":
        raise RuntimeError(f"Kakao HTTP {code or r.returncode}: {body[:120]}")
    docs = json.loads(body).get("documents")
    if docs is None:
        raise RuntimeError("Kakao reply carried no documents")
    return docs


def geocode(entries, cache, key, log):
    """Pin every listed licence still lacking one. A query that answered with
    nothing is cached as a fact about the address; one that could not be made
    is not cached and is retried next run."""
    failures = 0
    for e in entries:
        if e.get("excluded") or "lat" in e:
            continue
        for q in (lookup_address(e["road"]), e["lot"]):
            if not q:
                continue
            if q not in cache:
                try:
                    docs = kakao_lookup(q, key)
                except (RuntimeError, ValueError, subprocess.SubprocessError) as ex:
                    log(f"  geocode not made for {q}: {ex}")
                    failures += 1
                    break
                cache[q] = ([float(docs[0]["y"]), float(docs[0]["x"])]
                            if docs else None)
                time.sleep(KAKAO_SPACING)
            if cache[q]:
                e["lat"], e["lon"] = cache[q]
                break
    return failures


def write_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True))
    os.replace(tmp, path)


def main(argv):
    dry = "--dry-run" in argv
    unknown = [a for a in argv if a != "--dry-run"]
    if unknown:
        sys.exit(f"unknown arguments: {unknown}")
    log = lambda m: print(m, flush=True)
    key = keychain(*KEYCHAIN)
    if not key:
        log("NOT CHECKED: no Keychain item seoul-open-data")
        return 2
    DATA.mkdir(exist_ok=True)
    try:
        state = json.loads(STATE.read_text())
    except FileNotFoundError:
        state = {"licences": {}, "totals": {}}
    licences, totals = state["licences"], state["totals"]
    today = dt.datetime.now(SEOUL).date()
    late = (today - dt.timedelta(days=LATE_DAYS)).isoformat()
    first = (today - dt.timedelta(days=FIRST_RUN_DAYS)).isoformat()
    not_checked, added, closed, unknown_types = [], 0, 0, set()

    for svc, district, register in services():
        t0 = time.time()
        try:
            rows, total = read_all(svc, key)
        except (RuntimeError, ValueError, subprocess.SubprocessError) as ex:
            not_checked.append(f"{svc}: {ex}")
            continue
        bad = check_list(rows, totals.get(svc), DISTRICTS[district][1])
        if bad:
            not_checked.append(f"{svc}: {bad}")
            continue
        # A register never read before (a district just added) starts with
        # the first-run window, so its archive reaches as far back as the others'.
        floor = late if svc in totals else first
        totals[svc] = len(rows)
        new_here, closed_here, unknown_here = merge(licences, rows, district, register,
                                                    today.isoformat(), floor)
        added += new_here
        closed += closed_here
        unknown_types |= unknown_here
        log(f"{svc} {len(rows)} rows, {new_here} new, {time.time() - t0:.0f}s")

    for e in licences.values():
        e["excluded"] = reexclude(e)
    listed = [e for e in licences.values() if not e["excluded"]]
    log(f"tracked {len(licences)}, listed {len(listed)}; "
        f"this run added {added}, closed {closed}")
    rc = 0
    if unknown_types:
        log(f"types not in the table (kept in Korean): {sorted(unknown_types)}")
        rc = 1
    if dry:
        log("dry run: nothing written, nothing geocoded")
    else:
        kkey = keychain(*KAKAO_KEYCHAIN)
        try:
            cache = json.loads(GEOCODE_CACHE.read_text())
        except FileNotFoundError:
            cache = {}
        if not kkey:
            log("geocode NOT CHECKED: no Kakao key in the Keychain")
            rc = max(rc, 1)
        elif geocode(listed, cache, kkey, log):
            rc = max(rc, 1)
        unpinned = sum("lat" not in e for e in listed)
        log(f"pinned {len(listed) - unpinned} of {len(listed)}")
        write_json(GEOCODE_CACHE, cache)
        state["updated"] = dt.datetime.now(SEOUL).isoformat(timespec="minutes")
        state["newest_licence"] = max((e["licensed"] for e in licences.values()), default=None)
        write_json(STATE, state)
    for n in not_checked:
        log(f"NOT CHECKED {n}")
    return 2 if not_checked else rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
