#!/usr/bin/env python3
"""Now Serving Seoul: the daily digest card for Bluesky.

One post a day (his call, 10 October 2026): a card summing up one licence
date, with the whole list in the alt text and the site linked in the post.

    python3 nss_card.py --draft                  # the next day to post
    python3 nss_card.py --draft --day 2026-10-26 # a given licence date

A draft writes drafts/<day>.png and prints the post text and alt text. It
posts nothing: posting is not built yet.

Which day: a licence date is posted only once a LATER licence date is on
record, because the register publishes a day in pieces (on 28 October 2026
Oct. 27 had 1 licence and Oct. 26 had 31). That is a rule of thumb, not a
guarantee: a day can still grow after it is posted, and the card is then a
snapshot. A failed harvest leaves no later day, so nothing posts, never a
short day.

Rendering: headless Chrome onto a magenta page, cropped to the card by
Pillow (the Seoul Index pattern). ⚠️ Bluesky fits a lone image in a SQUARE
box, so a portrait card is drawn narrower; `render()` checks the card is
landscape and says so when it is not, and the card carries a few names
rather than all of them for that reason.
"""
import argparse
import datetime as dt
import html
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

from nss_common import DISTRICTS, GROUPS, HERE, STATE
import nss_build as b

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DRAFTS = HERE / "drafts"
SENTINEL = (255, 0, 255)
CARD_WIDTH = 600          # CSS px; rendered at 2x
HIGHLIGHTS = 5
SITE = "nowservingseoul.com"
# One word per kind, singular and plural, for the counts line.
KIND_WORDS = {"restaurant": ("restaurant", "restaurants"),
              "bar": ("bar", "bars"),
              "cafe": ("café or bakery", "cafés and bakeries")}


class CardRenderError(RuntimeError):
    pass


def esc(s):
    return html.escape(s or "", quote=True)


# Cuisines named for a place keep their capital in running text.
PROPER = ("Korean", "Japanese", "Chinese", "Western")


def kind_text(type_en):
    """"Chinese" stays, "Restaurant" -> "restaurant", for the alt text."""
    if type_en.split(" ")[0] in PROPER:
        return type_en
    return type_en[:1].lower() + type_en[1:]


def plural(n, kind):
    one, many = KIND_WORDS[kind]
    return f"{n} {one if n == 1 else many}"


def by_day(entries):
    days = {}
    for e in entries:
        days.setdefault(e["date"], []).append(e)
    return days


def complete_days(entries):
    """Licence dates with a later licence date on record, oldest first."""
    days = sorted(by_day(entries))
    return days[:-1]


def next_day(entries, posted):
    """The newest complete day, if it is later than every day already posted;
    else None. Only forward: once Oct. 26 has posted, an older day that never
    did (a stalled harvest, a failed run) is left alone rather than posted a
    week late out of order."""
    days = complete_days(entries)
    if not days:
        return None
    last = max((dt.date.fromisoformat(d) for d in posted), default=None)
    return days[-1] if last is None or days[-1] > last else None


def is_branch(e):
    """A chain's branch: the licence name ends in 점 ("…대치역점") or the
    English says "branch". Ranked last on the card: 7-Eleven and Banapresso
    led the first drafts (29 October 2026), the least interesting places."""
    return e["name"].rstrip().endswith("점") or "branch" in (e.get("name_en") or "").lower()


def highlights(es, n=HIGHLIGHTS):
    """A few places for the card: any a blog post says has opened first, then
    independents before chain branches, one at a time across kinds and
    districts so the few are not all Gangnam restaurants. Deterministic, so a
    redraft of a day gives the same card."""
    pool = sorted(es, key=lambda e: (not e.get("opened"), e["name_en"] or e["name"]))
    chosen, kinds, districts = [], Counter(), Counter()
    while pool and len(chosen) < n:
        pick = min(pool, key=lambda e: (not e.get("opened"), is_branch(e), kinds[e["group"]],
                                        districts[e["district"]]))
        pool.remove(pick)
        chosen.append(pick)
        kinds[pick["group"]] += 1
        districts[pick["district"]] += 1
    return chosen


def card_name(en):
    """The card's English name without a trailing gloss: "Susu Gimbap (seaweed
    rice rolls)" -> "Susu Gimbap". The gloss pushed names off the card's row;
    the alt text keeps it."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", en or "").strip()


def summary(day, es):
    kinds = Counter(e["group"] for e in es)
    districts = Counter(DISTRICTS[e["district"]][0] for e in es)
    return kinds, sorted(districts.items(), key=lambda kv: (-kv[1], kv[0]))


def headline(n):
    return f"{n} new place{'' if n == 1 else 's'} licensed"


def build_html(day, es):
    kinds, districts = summary(day, es)
    kind_html = "".join(
        f'<span class="k"><span class="dot {k}"></span>{plural(kinds[k], k)}</span>'
        for k in GROUPS if kinds[k])
    rows = []
    for e in highlights(es):
        en = card_name(e.get("name_en"))
        ko = e["name"]
        name = (f'{esc(en)} <span class="ko" lang="ko">{esc(ko)}</span>'
                if en and en != ko else f'<span lang="ko">{esc(ko)}</span>')
        tag = '<span class="op">Opened</span>' if e.get("opened") else ""
        rows.append(f'<li><span class="dot {e["group"]}"></span><span class="nm">{name}</span>'
                    f'{tag}<span class="wh">{esc(e["type_en"])}, '
                    f'{esc(DISTRICTS[e["district"]][0])}</span></li>')
    more = len(es) - len(rows)
    more_html = (f'<p class="more">and {more} more at <b>{SITE}</b></p>' if more > 0
                 else f'<p class="more">More at <b>{SITE}</b></p>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:#ff00ff}}
.card{{width:{CARD_WIDTH}px;background:#fbfaf7;color:#1d1b18;
font:15px/1.4 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;
border-top:8px solid #c2410c;padding:20px 26px 18px;box-sizing:border-box}}
.mast{{display:flex;justify-content:space-between;align-items:baseline;
font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6a645b}}
.mast b{{color:#c2410c;letter-spacing:.1em}}
h1{{font:700 34px/1.1 Georgia,"Times New Roman",serif;margin:10px 0 2px;letter-spacing:-.01em}}
.date{{font:italic 17px Georgia,serif;color:#6a645b;margin:0 0 12px}}
.kinds{{display:flex;flex-wrap:wrap;gap:4px 18px;margin:0 0 16px}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;flex:none}}
.dot.restaurant{{background:#c2410c}}.dot.bar{{background:#7c3aed}}.dot.cafe{{background:#0f766e}}
h2{{font:600 12px/1 -apple-system,sans-serif;letter-spacing:.08em;text-transform:uppercase;
color:#6a645b;margin:0 0 6px;padding-top:10px;border-top:1px solid #e4dfd6}}
ul{{list-style:none;margin:0;padding:0}}
li{{display:flex;align-items:baseline;gap:0;padding:3px 0}}
li .dot{{position:relative;top:-1px}}
.nm{{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}}
.ko{{font-weight:400;color:#6a645b;margin-left:5px}}
.op{{font-size:11px;font-weight:600;color:#fff;background:#0f766e;border-radius:3px;
padding:0 5px;margin-left:7px;flex:none}}
.wh{{margin-left:auto;padding-left:12px;color:#6a645b;font-size:13px;white-space:nowrap;flex:none}}
.more{{margin:8px 0 0;font-size:13px;color:#6a645b}}.more b{{color:#c2410c;font-weight:600}}
</style></head><body><div class="card">
<div class="mast"><b>Now Serving Seoul</b><span>Seoul’s new food licenses</span></div>
<h1>{headline(len(es))}</h1>
<p class="date">{b.day_text(day)}</p>
<div class="kinds">{kind_html}</div>
<h2>Among them</h2><ul>{"".join(rows)}</ul>{more_html}
</div></body></html>"""


MAP_WIDTH = 600          # CSS px, like the card
MAP_PAD = 34
KIND_COLORS = {"restaurant": "#c2410c", "bar": "#7c3aed", "cafe": "#0f766e"}


def project(points, keep=()):
    """lon/lat -> x/y on a MAP_WIDTH canvas. A flat projection with longitude
    shrunk by cos(latitude): over one city that is as true as Web Mercator to
    the eye, with no tiles needed. The frame is fitted to the middle 98
    percent of `points` (a few strays left a band of empty map) and widened to
    take in every point in `keep`, the day's places, so none falls off."""
    lat0 = sum(la for _, la in points) / len(points)
    k = math.cos(math.radians(lat0))
    xs = sorted(lo * k for lo, _ in points)
    ys = sorted(-la for _, la in points)
    cut = len(points) // 100
    x0, x1 = xs[cut], xs[-1 - cut]
    y0, y1 = ys[cut], ys[-1 - cut]
    for lo, la in keep:
        x0, x1 = min(x0, lo * k), max(x1, lo * k)
        y0, y1 = min(y0, -la), max(y1, -la)
    scale = (MAP_WIDTH - 2 * MAP_PAD) / (x1 - x0)
    height = (y1 - y0) * scale + 2 * MAP_PAD

    def to_xy(lon, lat):
        return MAP_PAD + (lon * k - x0) * scale, MAP_PAD + (-lat - y0) * scale
    return to_xy, height


def map_html(day, es, backdrop):
    """The thread's second post: every place the site has ever tracked as
    faint dots, which draw the eight districts by themselves, and the day's
    places on top in their kinds' colours, each district labelled with its
    count. Drawn from our own data: OpenStreetMap's tile policy rules out
    fetching tiles for an image nobody is viewing (read 29 October 2026)."""
    pts = [(e["lon"], e["lat"]) for e in backdrop]
    to_xy, height = project(pts, [(e["lon"], e["lat"]) for e in es if "lat" in e])
    grey = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6"/>'
                   for x, y in (to_xy(*p) for p in pts)
                   if -4 < x < MAP_WIDTH + 4 and -4 < y < height + 4)
    today = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{KIND_COLORS[e["group"]]}"/>'
        for e in sorted(es, key=lambda e: e["group"])
        if "lat" in e for x, y in [to_xy(e["lon"], e["lat"])])
    counts = Counter(e["district"] for e in es)
    labels = []
    for code, (name, _) in DISTRICTS.items():
        mine = [to_xy(e["lon"], e["lat"]) for e in backdrop if e["district"] == code]
        if not mine:
            continue
        mx = sorted(x for x, _ in mine)[len(mine) // 2]
        my = sorted(y for _, y in mine)[len(mine) // 2]
        n = counts.get(code, 0)
        labels.append(f'<text x="{mx:.1f}" y="{my:.1f}" class="{"on" if n else "off"}">'
                      f'{esc(name)}{f" <tspan>{n}</tspan>" if n else ""}</text>')
    legend = "".join(
        f'<span><i style="background:{KIND_COLORS[k]}"></i>{GROUPS[k]}</span>' for k in GROUPS)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:#ff00ff}}
.card{{width:{MAP_WIDTH}px;background:#fbfaf7;color:#1d1b18;
font:14px/1.4 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;
border-top:8px solid #c2410c;padding:16px 0 12px;box-sizing:border-box}}
.mast{{display:flex;justify-content:space-between;align-items:baseline;padding:0 26px;
font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6a645b}}
.mast b{{color:#c2410c;letter-spacing:.1em}}
svg{{display:block}}
.bg circle{{fill:#ddd5c8}}
text{{font:600 14px -apple-system,sans-serif;text-anchor:middle;paint-order:stroke;
stroke:#fbfaf7;stroke-width:5px;stroke-linejoin:round}}
text.on{{fill:#1d1b18}}text.off{{fill:#a39c90;font-weight:400}}
text tspan{{fill:#c2410c;font-weight:700}}
.foot{{display:flex;justify-content:space-between;align-items:center;padding:0 26px;
font-size:12px;color:#6a645b}}
.foot span{{margin-right:14px}}
.foot i{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}}
</style></head><body><div class="card">
<div class="mast"><b>Where they are</b><span>{b.day_text(day)}</span></div>
<svg width="{MAP_WIDTH}" height="{height:.0f}" viewBox="0 0 {MAP_WIDTH} {height:.0f}">
<g class="bg">{grey}</g><g>{today}</g><g>{"".join(labels)}</g></svg>
<div class="foot"><div>{legend}</div><div>Gray: every place listed so far</div></div>
</div></body></html>"""


def map_alt(day, es):
    _, districts = summary(day, es)
    return (f"Map of the {len(es)} places licensed on {b.day_text(day)}, by district: "
            + ", ".join(f"{n} {c}" for n, c in districts)
            + ". Each is a dot colored by kind, over gray dots for every place listed so far.")


def render(page, out):
    """HTML -> cropped PNG at 2x. Returns (path, (w, h))."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "card.html"
        shot = Path(tmp) / "shot.png"
        src.write_text(page)
        r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--force-device-scale-factor=2", f"--window-size={CARD_WIDTH},1600",
                            "--default-background-color=FF00FFFF",
                            f"--screenshot={shot}", src.as_uri()],
                           capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        if not shot.exists():
            raise CardRenderError(f"Chrome made no screenshot: {r.stderr.strip()[-300:]}")
        img = Image.open(shot).convert("RGB")
        box = ImageChops.difference(img, Image.new("RGB", img.size, SENTINEL)).getbbox()
        if not box:
            raise CardRenderError("the screenshot is all background")
        card = img.crop(box)
        out.parent.mkdir(parents=True, exist_ok=True)
        card.save(out, optimize=True)
    w, h = card.size
    if h > w:
        print(f"⚠️ card is portrait ({w}x{h}): Bluesky will draw it narrower", file=sys.stderr)
    return out, (w, h)


def alt_text(day, es):
    kinds, districts = summary(day, es)
    lines = [f"Now Serving Seoul: {headline(len(es))} on {b.day_text(day)}.",
             "By kind: " + ", ".join(plural(kinds[k], k) for k in GROUPS if kinds[k]) + ".",
             "By district: " + ", ".join(f"{n} {c}" for n, c in districts) + ".",
             "All of them:"]
    for e in sorted(es, key=lambda e: (DISTRICTS[e["district"]][0], e["name_en"] or e["name"])):
        en = e.get("name_en")
        name = f"{en} ({e['name']})" if en and en != e["name"] else e["name"]
        lines.append(f"{name}, {kind_text(e['type_en'])}, {DISTRICTS[e['district']][0]}"
                     + (", opened" if e.get("opened") else "") + ".")
    return "\n".join(lines)


def post_text(day, es):
    return (f"{headline(len(es))} in Seoul on {b.day_text(day)}. "
            f"The full list, with a map: {SITE}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--draft", action="store_true", required=True,
                    help="render the card and print the post; posts nothing")
    ap.add_argument("--day", help="licence date, YYYY-MM-DD (default: the next to post)")
    args = ap.parse_args()
    entries = b.listed(json.loads(STATE.read_text()))
    days = by_day(entries)
    if args.day:
        day = dt.date.fromisoformat(args.day)
        if day not in days:
            sys.exit(f"no listed licences on {day}")
    else:
        day = next_day(entries, posted=set())
        if day is None:
            sys.exit("no complete day to post")
    es = days[day]
    state = json.loads(STATE.read_text())
    backdrop = [e for e in state["licences"].values()
                if "lat" in e and not e.get("excluded") and e["district"] in DISTRICTS]
    path, (w, h) = render(build_html(day, es), DRAFTS / f"{day}.png")
    mpath, (mw, mh) = render(map_html(day, es, backdrop), DRAFTS / f"{day}-map.png")
    print(f"card: {path} ({w}x{h})\nmap: {mpath} ({mw}x{mh})\n\npost text:\n"
          f"{post_text(day, es)}\n\nalt text:\n{alt_text(day, es)}\n\nmap alt text:\n"
          f"{map_alt(day, es)}")


if __name__ == "__main__":
    main()
