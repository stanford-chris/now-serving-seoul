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
    """The newest complete day not yet posted, or None."""
    for d in reversed(complete_days(entries)):
        if d.isoformat() not in posted:
            return d
    return None


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
    top = max(c for _, c in districts)
    dist_html = "".join(
        f'<div class="d"><span class="dn">{esc(name)}</span>'
        f'<span class="meter"><span style="width:{100 * c / top:.1f}%"></span></span>'
        f'<span class="dc">{c}</span></div>' for name, c in districts)
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
.kinds{{display:flex;flex-wrap:wrap;gap:4px 18px;margin:0 0 12px}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;flex:none}}
.dot.restaurant{{background:#c2410c}}.dot.bar{{background:#7c3aed}}.dot.cafe{{background:#0f766e}}
.dists{{display:grid;grid-template-columns:1fr 1fr;gap:3px 22px;margin:0 0 14px;font-size:13px}}
.d{{display:flex;align-items:center;gap:8px}}
.dn{{width:74px;flex:none}}.dc{{width:18px;text-align:right;font-variant-numeric:tabular-nums;color:#6a645b}}
/* "meter", never "bar": .dot.bar is the bars' dot, and a shared class stretched it. */
.meter{{flex:1;height:6px;background:#efe9df;border-radius:3px;overflow:hidden}}
.meter span{{display:block;height:100%;background:#c2410c;opacity:.75}}
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
<div class="dists">{dist_html}</div>
<h2>Among them</h2><ul>{"".join(rows)}</ul>{more_html}
</div></body></html>"""


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
    path, (w, h) = render(build_html(day, es), DRAFTS / f"{day}.png")
    print(f"card: {path} ({w}x{h})\n\npost text:\n{post_text(day, es)}\n\nalt text:\n{alt_text(day, es)}")


if __name__ == "__main__":
    main()
