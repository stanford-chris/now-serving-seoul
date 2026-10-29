# Now Serving Seoul

New restaurant, bar and café licenses in eight Seoul districts, in English, at
[nowservingseoul.com](https://nowservingseoul.com).

Gangnam, Jongno, Jung, Mapo, Seocho, Seongdong, Songpa and Yongsan. Rebuilt daily from
Seoul’s food-license register.

## How it works

| Step | Script | What it does |
| --- | --- | --- |
| Harvest | `nss_harvest.py` | Reads 16 registers (two per district), keeps every new operating license by its management number, marks closures, pins each place with Kakao’s address search |
| Build | `nss_build.py` | Writes `public/`: the last 14 days with a map and filters, one page per week, an index of weeks, an about page |
| Deploy | `deploy.sh` | Harvest, build, `wrangler deploy` to the Worker `now-serving-seoul` |

A license is not an opening. Every place is listed as **newly licensed**; it
becomes **opened** only when a post about it says so (the weekly pass, not yet
built).

## Left out

Convenience stores, food trucks, caterers, counters in stations, cinemas,
motorway stops and department stores; licenses whose name marks them temporary
(한시적), and anything at a department-store or food-hall address. Measured over
the 30 days to 8 October 2026: 572 licenses listed before these filters, of
which 61 were marked temporary and 86 sat in a food hall.

## Traps

- **`_JR` is Jungnang-gu, not Jongno.** Jongno is `_JN`. Every register’s
  addresses are checked against its district, and a mismatch is NOT CHECKED.
- **The API’s paging is unstable.** Rows are unsorted and each full read repeats
  some and skips others, so reads are unioned until the total is reached.
- **A short read never closes anything.** A register reading under 98% of its
  last good total is NOT CHECKED, and a license missing from a read is left as
  it was; only the register saying “closed” closes one.

## Sources and credits

- License data: Seoul Metropolitan Government, data.seoul.go.kr
  (서울시 일반음식점 인허가 정보 and 휴게음식점 인허가 정보), KOGL Type 1.
- Locations: Kakao Local address search.
- Map: Leaflet, tiles © OpenStreetMap contributors.

## Tests

```bash
python3 -m unittest test_nss
```

## Email interest counter

The home and About pages carry a short box asking which districts, and how often, a reader
would want the list by email. It is a counter, not a sign-up: no email address is asked for
or stored. `src/worker.js` answers `/api/*` only and writes one Workers KV key per vote, with
the choices in the key's metadata; every other path is served from the static build as
before. The totals are at `/api/interest/totals` behind a bearer token, and the owner's
morning digest reads them.
