#!/usr/bin/env python3
"""Build the Now Serving Seoul site from data/licences.json into public/.

    python3 nss_build.py

Pages:
  /                       the last RECENT_DAYS days of licences, map and list
  /weeks/                 every week on record
  /week/YYYY-MM-DD/       one week (Monday to Sunday) by licence date

The list is in the HTML itself, so the page reads without JavaScript; the
filters and the map are added on top. A licence is "newly licensed" until the
weekly pass finds a post saying the place has opened.
"""
import datetime as dt
import html
import json
import os
import shutil
import sys
import urllib.parse
from collections import defaultdict

from nss_common import (DISTRICTS, GROUPS, HERE, NEIGHBORHOODS, PUBLIC, STATE,
                        district_count, display_name, lookup_address)

BRAND = HERE / "brand"
NAMES = HERE / "data" / "names.json"
BLOGS = HERE / "data" / "blogs.json"

RECENT_DAYS = 14
# The home page intro, his wording (10 October 2026); the districts themselves
# are named on the About page.
HOME_INTRO = [
    f"This site lists the newly licensed restaurants, bars and cafés in {district_count()} "
    f"districts of Seoul that are popular with visitors and newcomers. Every place that serves "
    f"food needs a license from its district office, which is published as open data. The site "
    f"reads the registers every day, so a new place usually appears here within a few days of "
    f"its license.",
]
SITE = "https://nowservingseoul.com"
LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def esc(s):
    return html.escape(s or "", quote=True)


# AP style, his call (10 October 2026): a month with a date is abbreviated
# except March to July, which are never abbreviated; a weekday never is.
AP_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.",
             "Oct.", "Nov.", "Dec."]


def day_text(d, weekday=True, year=False):
    """AP style: "Thursday, Oct. 8", "Oct. 8, 2026", "June 3"."""
    s = f"{AP_MONTHS[d.month - 1]} {d.day}"
    if year:
        s += f", {d.year}"
    return f"{WEEKDAYS[d.weekday()]}, {s}" if weekday else s


def stamp_text(iso):
    """"2026-10-10T18:12" -> "Oct. 10, 2026, 6:12 p.m.". House style
    a.m./p.m.; the raw string if it does not parse."""
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "unknown"
    h = t.hour % 12 or 12
    return f"{day_text(t.date(), weekday=False, year=True)}, {h}:{t.minute:02d} " \
           f"{'a.m.' if t.hour < 12 else 'p.m.'}"


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def load(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def listed(state, names=None, blogs=None):
    """Every place shown, newest first. English name, in order of preference:
    a blog post's (nss_blogs.py), the licence's own bracketed English, the
    model's (nss_names.py)."""
    names = load(NAMES) if names is None else names
    blogs = load(BLOGS) if blogs is None else blogs
    out = []
    for mgt, e in state["licences"].items():
        if e.get("excluded") or e.get("status") == "closed":
            continue
        try:
            d = dt.date.fromisoformat(e["licensed"])
        except (KeyError, ValueError):
            continue
        name = display_name(e["name"])
        b = blogs.get(mgt) or {}
        if b.get("delivery_only"):
            continue
        out.append(dict(e, id=mgt, date=d, name=name,
                        name_en=b.get("english") or e.get("name_en") or names.get(name),
                        opened=b.get("opened"), about=b.get("about")))
    # One place, two licences: the register sometimes holds the same name at
    # the same street address twice (초초맛차, 을지로 281, on 8 October 2026,
    # once with "DDP 팔거리" after the comma). The earlier licence stands.
    out.sort(key=lambda e: (e["date"], e["id"]))
    seen, unique = set(), []
    for e in out:
        k = (e["name"], lookup_address(e["road"]) or e["lot"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    unique.sort(key=lambda e: (e["date"], e["name"]), reverse=True)
    return unique


def kakao_link(e):
    if "lat" in e:
        return ("https://map.kakao.com/link/map/"
                + urllib.parse.quote(f"{e['name']},{e['lat']},{e['lon']}", safe=","))
    return "https://map.kakao.com/link/search/" + urllib.parse.quote(f"{e['name']} {e['road']}")


def entry_html(e):
    district = DISTRICTS[e["district"]][0]
    where = f"{district}, {esc(e['dong'])}" if e.get("dong") else district
    if e.get("name_en") and e["name_en"] != e["name"]:
        title = f'{esc(e["name_en"])} <span class="ko" lang="ko">{esc(e["name"])}</span>'
    else:
        title = f'<span lang="ko">{esc(e["name"])}</span>'
    opened = e.get("opened")
    if opened:
        posted = dt.date.fromisoformat(opened["posted"])
        status = (f'<span class="status opened">Opened</span> '
                  f'<a class="status" href="{esc(opened["url"])}">blog post, '
                  f'{day_text(posted, weekday=False)}</a>')
    else:
        status = '<span class="status">Newly licensed</span>'
    about = f'<p class="about">{esc(e["about"])}</p>' if e.get("about") else ""
    return (f'<li class="{e["group"]}" data-district="{e["district"]}" data-group="{e["group"]}" '
            f'data-date="{e["date"].isoformat()}" data-type="{esc(e["type_en"])}">'
            f'<h3>{title}</h3>{about}'
            f'<p class="meta"><span class="chip {e["group"]}">{esc(e["type_en"])}</span>'
            f'<span class="chip place">{where}</span>{status}</p>'
            f'<p class="addr" lang="ko">{esc(e["road"] or e["lot"])} '
            f'<a href="{esc(kakao_link(e))}">Kakao Map</a></p></li>')


def list_html(entries):
    by_day = defaultdict(list)
    for e in entries:
        by_day[e["date"]].append(e)
    parts = []
    for d in sorted(by_day, reverse=True):
        items = by_day[d]
        parts.append(f'<section class="day"><h2>Licensed {day_text(d)} '
                     f'<span class="count">{len(items)}</span></h2><ul>'
                     + "".join(entry_html(e) for e in items) + "</ul></section>")
    return "".join(parts) or "<p>No licenses in this period.</p>"


def filters_html(entries):
    counts = defaultdict(int)
    for e in entries:
        counts[e["district"]] += 1
    districts = "".join(
        f'<option value="{k}">{v[0]}</option>'
        for k, v in sorted(DISTRICTS.items(), key=lambda kv: kv[1][0]) if counts[k])
    groups = "".join(
        f'<label><input type="checkbox" value="{k}" checked> '
        f'<span class="dot {k}" aria-hidden="true"></span>{v}</label>' for k, v in GROUPS.items())
    return (f'<form class="filters" aria-label="Filter the list">'
            f'<label>District <select name="district"><option value="">All {district_count()}</option>'
            f'{districts}</select></label><div class="kinds" role="group" aria-labelledby="kinds">'
            f'<span id="kinds" class="label">Kind of place</span>{groups}'
            f'</div><p class="shown" aria-live="polite"></p></form>')


def points(entries):
    return [{"n": e["name"], "e": e.get("name_en") or "", "t": e["type_en"],
             "g": e["group"], "d": e["district"], "y": e["lat"], "x": e["lon"],
             "k": kakao_link(e)} for e in entries if "lat" in e]


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b18;--muted:#6a645b;--rule:#e4dfd6;--card:#fff;
--accent:#c2410c;--restaurant:#c2410c;--bar:#7c3aed;--cafe:#0f766e;--band:#f6e7dc;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141311;--fg:#ece8e1;
--muted:#a39c90;--rule:#2e2b27;--card:#1c1a17;--accent:#fb923c;--restaurant:#fb923c;
--bar:#a78bfa;--cafe:#2dd4bf;--band:#24190f}}
:root[data-theme="dark"]{--bg:#141311;--fg:#ece8e1;--muted:#a39c90;--rule:#2e2b27;
--card:#1c1a17;--accent:#fb923c;--restaurant:#fb923c;--bar:#a78bfa;--cafe:#2dd4bf;--band:#24190f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,
BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:0 16px}

h1{font:700 2.2rem/1.1 Georgia,"Times New Roman",serif;margin:0 0 8px;letter-spacing:-.01em}
h1 a{color:inherit;text-decoration:none}
.lede{color:var(--muted);margin:0 0 10px;max-width:46em}
a{color:var(--accent)}
nav.top{font-size:.95rem;margin:8px 0 16px}
#map{height:420px;border-radius:10px;border:1px solid var(--rule);margin:8px 0 16px;
background:var(--card)}
.filters{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;padding:12px 0;
border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
/* A div, not a fieldset: Safari puts a fieldset's legend on a line of its own. */
.kinds{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px}
.kinds .label{color:var(--muted)}
.filters select{font:inherit;padding:2px 6px}
.shown{margin:0;color:var(--muted);font-size:.9rem;flex-basis:100%}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;
vertical-align:baseline}
.dot.restaurant{background:var(--restaurant)}.dot.bar{background:var(--bar)}
.dot.cafe{background:var(--cafe)}
.day h2{font:600 1.15rem/1.3 Georgia,serif;margin:28px 0 8px;padding-bottom:6px;
border-bottom:1px solid var(--rule)}
.count{color:var(--muted);font:400 .9rem system-ui,sans-serif;margin-left:6px}
ul{list-style:none;margin:0;padding:0}
li{padding:10px 0;border-bottom:1px solid var(--rule)}
li h3{font-size:1.05rem;margin:0}
li .ko{color:var(--muted);font-weight:400;margin-left:6px}
.about{font-style:italic;margin:2px 0 4px}
.prose{max-width:40em}.prose h3{font:600 1.05rem Georgia,serif;margin:22px 0 4px}
ul.plain{list-style:disc;padding-left:20px}ul.plain li{border:0;padding:2px 0;margin:0}
.status.opened{color:var(--cafe);font-weight:700}
li p{margin:2px 0}
.meta{font-size:.92rem}
.addr{font-size:.85rem;color:var(--muted);overflow-wrap:anywhere}
.status{color:var(--muted)}
li[hidden],.day[hidden]{display:none}
footer{margin:40px 0;padding-top:16px;border-top:1px solid var(--rule);color:var(--muted);
font-size:.88rem}
.weeks li{display:flex;justify-content:space-between}
.leaflet-container{font:inherit}
.band{background:var(--band);border-bottom:1px solid var(--rule)}
.head{display:flex;gap:18px;align-items:center;padding:28px 16px 18px}
.mark img{display:block;border-radius:50%;width:64px;height:64px}
.band h1{margin:0 0 4px}
nav.top{display:flex;gap:16px;margin:10px 0 0}
nav.top a{font-weight:600;text-decoration:none}
nav.top a:hover{text-decoration:underline}
.filters{position:sticky;top:0;z-index:1000;background:var(--bg)}
li{padding:12px 0 12px 14px;border-left:4px solid var(--rule);margin:8px 0;border-bottom:0}
li.restaurant{border-left-color:var(--restaurant)}li.bar{border-left-color:var(--bar)}
li.cafe{border-left-color:var(--cafe)}
.chip{display:inline-block;font-size:.8rem;padding:1px 8px;border-radius:999px;margin:2px 6px 2px 0;
background:color-mix(in srgb,var(--fg) 8%,transparent)}
.chip.restaurant{background:color-mix(in srgb,var(--restaurant) 18%,transparent)}
.chip.bar{background:color-mix(in srgb,var(--bar) 20%,transparent)}
.chip.cafe{background:color-mix(in srgb,var(--cafe) 20%,transparent)}
.meta .status{font-size:.85rem}
@media (max-width:600px){.head{align-items:flex-start}.mark img{width:48px;height:48px}}
/* Dark map tiles: OpenStreetMap serves only light ones, so they are inverted
   and turned back to their own hues. Markers sit in another pane, untouched. */
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .leaflet-tile-pane{
filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9)}}
:root[data-theme="dark"] .leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9)}
@media (max-width:600px){h1{font-size:1.8rem}#map{height:320px}}
"""

SCRIPT = """
(function(){
var P=JSON.parse(document.getElementById('points').textContent);
var form=document.querySelector('.filters'),shown=document.querySelector('.shown');
var map=null,layer=null,css=getComputedStyle(document.documentElement);
function colour(g){return css.getPropertyValue('--'+g).trim()}
if(window.L&&document.getElementById('map')){
 map=L.map('map',{scrollWheelZoom:false});
 L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,
  attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
 layer=L.layerGroup().addTo(map);
}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}
function apply(){
 var d=form.district.value,g={};
 form.querySelectorAll('input[type=checkbox]').forEach(function(c){g[c.value]=c.checked});
 var n=0;
 document.querySelectorAll('.day').forEach(function(s){
  var any=false;
  s.querySelectorAll('li').forEach(function(li){
   var ok=(!d||li.dataset.district===d)&&g[li.dataset.group];
   li.hidden=!ok;if(ok){any=true;n++}});
  s.hidden=!any;});
 shown.textContent=n+(n===1?' place':' places')+' shown';
 if(layer){layer.clearLayers();var b=[];
  P.forEach(function(p){if((d&&p.d!==d)||!g[p.g])return;
   var m=L.circleMarker([p.y,p.x],{radius:6,weight:1,color:'#fff',fillColor:colour(p.g),fillOpacity:.9});
   m.bindPopup((p.e?'<strong>'+esc(p.e)+'</strong><br><span lang="ko">'+esc(p.n)+'</span>':'<strong lang="ko">'+esc(p.n)+'</strong>')+'<br>'+esc(p.t)+
    '<br><a href="'+p.k+'">Kakao Map</a>');
   m.addTo(layer);b.push([p.y,p.x]);});
  map.invalidateSize();
  if(b.length)map.fitBounds(b,{padding:[20,20],maxZoom:15});else map.setView([37.55,126.99],12);}
}
form.addEventListener('change',apply);apply();
// The first fit can run before the page has its final size (seen in a
// freshly opened pane: zoom 15 on the centre); fit again once it has.
window.addEventListener('load',apply);
})();
"""


def page(title, lede, body, entries, path, with_map=True, with_filters=True):
    canonical = SITE + path
    paras = lede if isinstance(lede, list) else [lede]
    lede = " ".join(paras)
    lede_html = "".join(f'<p class="lede">{esc(p)}</p>' for p in paras)
    pts = json.dumps(points(entries), ensure_ascii=False).replace("</", "<\\/")
    head_map = (f'<link rel="stylesheet" href="{LEAFLET}/leaflet.min.css">'
                f'<script src="{LEAFLET}/leaflet.min.js"></script>') if with_map else ""
    map_div = ('<div id="map" role="region" aria-label="Map of the places listed below"></div>'
               if with_map else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(lede)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(lede)}">
<meta property="og:url" content="{canonical}">
<link rel="icon" href="/favicon.ico" sizes="32x32 64x64">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{head_map}<style>{CSS}</style></head><body>
<header class="band"><div class="wrap head">
<a href="/" class="mark"><img src="/favicon.svg" width="64" height="64" alt=""></a>
<div><h1><a href="/">Now Serving Seoul</a></h1>{lede_html}
<nav class="top"><a href="/">Latest</a><a href="/weeks/">Every week</a><a href="/about/">About</a></nav></div>
</div></header><div class="wrap">
<main>{filters_html(entries) if with_filters else ""}{map_div}{body}</main>
<footer><p>Data: Seoul Metropolitan Government
(<a href="https://www.kogl.or.kr/info/licenseType1.do">KOGL Type 1</a>), Kakao, OpenStreetMap.
<a href="/about/">About</a> · Made by <a href="https://chris-stanford.com/">Chris Stanford</a></p></footer></div>
<script type="application/json" id="points">{pts}</script>
{"<script>" + SCRIPT + "</script>" if with_filters else ""}</body></html>
"""


def about_page(state):
    districts = "".join(
        f"<li><strong>{DISTRICTS[k][0]}</strong>: {NEIGHBORHOODS[k]}</li>"
        for k in sorted(DISTRICTS, key=lambda k: DISTRICTS[k][0]))
    newest = (day_text(dt.date.fromisoformat(state["newest_licence"]), year=True)
              if state.get("newest_licence") else "unknown")
    body = f"""<section class="day prose"><h2>About</h2>
<p>Now Serving Seoul lists, in English, the newly licensed restaurants, bars and cafés in
{district_count()} districts of the city that are popular with visitors and newcomers. Every
place that serves food needs a license from its district office, which is published as open
data. The site reads the registers every day, so a new place usually appears here within a
few days of its license, often before anyone has written about it.</p>
<h3>Where</h3>
<ul class="plain">{districts}</ul>
<p>In the month ending Oct. 8, 2026, these districts accounted for 531 of the 1,191 places
that were licensed across all 25 of Seoul’s districts, after the exclusions below.</p>
<h3>Newly licensed, or opened?</h3>
<p>Every place starts as <strong>newly licensed</strong>. A license is permission to serve,
not proof that a place is serving: some open weeks later, and a few never do. Once a week,
each place licensed in the last six weeks is looked up on Naver’s blogs. When a post shows
the place open, at the same address, it is marked <strong>opened</strong> with a link to
that post and a one-line description. The post itself is never copied.</p>
<h3>Names</h3>
<p>Where the license gives a name in English, the site uses it. Otherwise the English name
is written by an A.I. model (Anthropic’s Claude): a Korean spelling of an English word
becomes that word, and anything else is romanized, with a short meaning when the name is
ordinary Korean words. When a blog post shows the place’s own English name, from its sign
or menu, that is used instead. The one-line descriptions of opened places are A.I.-written
too, from the posts. The Korean name from the license is always shown beside the English.</p>
<h3>Left out</h3>
<p>Convenience stores, food trucks, caterers, counters in stations, cinemas, motorway stops
and department stores; licenses marked temporary, which are almost all food-hall pop-ups;
anything at a department-store or food-hall address; and a second license for a place
already listed at the same address.</p>
<h3>How current</h3>
<p>The register runs a couple of days behind. The newest license on record is dated
{newest}; the site was last updated {esc(stamp_text(state.get("updated")))} (Seoul time).</p>
<h3>Sources</h3>
<p>License data: Seoul Metropolitan Government,
<a href="https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do">서울시 일반음식점 인허가 정보</a>
and its café counterpart, under KOGL Type 1. Locations from Kakao’s address search. Map
tiles © OpenStreetMap contributors. Posts from Naver blogs, linked, never copied.</p>
</section>"""
    return page("Now Serving Seoul · About", "How the list is made.", body, [], "/about/",
                with_map=False, with_filters=False)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    try:
        state = json.loads(STATE.read_text())
    except FileNotFoundError:
        sys.exit("no data/licences.json: run nss_harvest.py first")
    entries = listed(state)
    if not entries:
        sys.exit("refusing to build: no listed licences (a failed harvest, not a quiet city)")
    newest = entries[0]["date"]
    tmp = PUBLIC.with_name("public.tmp")
    shutil.rmtree(tmp, ignore_errors=True)

    recent = [e for e in entries if e["date"] > newest - dt.timedelta(days=RECENT_DAYS)]
    lede = HOME_INTRO
    write(tmp / "index.html", page("Now Serving Seoul", lede,
                                   list_html(recent), recent, "/"))

    weeks = defaultdict(list)
    for e in entries:
        weeks[monday(e["date"])].append(e)
    rows = []
    for m in sorted(weeks, reverse=True):
        es = weeks[m]
        label = f"Week of {day_text(m, weekday=False, year=True)}"
        write(tmp / "week" / m.isoformat() / "index.html",
              page(f"Now Serving Seoul · {label}",
                   f"{len(es)} restaurant, bar and café licenses, {day_text(m, weekday=False)} "
                   f"to {day_text(m + dt.timedelta(days=6), weekday=False)}.",
                   list_html(es), es, f"/week/{m.isoformat()}/"))
        rows.append(f'<li><a href="/week/{m.isoformat()}/">{label}</a><span>{len(es)}</span></li>')
    weeks_body = f'<section class="day weeks"><h2>Every week</h2><ul>{"".join(rows)}</ul></section>'
    write(tmp / "weeks" / "index.html",
          page("Now Serving Seoul · Every week", "Every week on record, by license date.",
               weeks_body, [], "/weeks/", with_map=False, with_filters=False))
    write(tmp / "about" / "index.html", about_page(state))
    # The site icon is the Bluesky avatar (brand/avatar.svg), so the two match.
    shutil.copy(BRAND / "avatar.svg", tmp / "favicon.svg")
    # favicon.ico and the PNG sizes come from brand/icons.js; Safari's tab
    # icon did not appear with the SVG alone (10 October 2026).
    shutil.copy(BRAND / "favicon.ico", tmp / "favicon.ico")
    shutil.copy(BRAND / "icon-180.png", tmp / "apple-touch-icon.png")
    write(tmp / "_headers", "/*\n  Cache-Control: public, max-age=300\n"
                            "  Referrer-Policy: strict-origin-when-cross-origin\n")

    shutil.rmtree(PUBLIC, ignore_errors=True)
    os.replace(tmp, PUBLIC)
    print(f"built {len(entries)} listed licences: {len(recent)} recent, {len(weeks)} weeks")


if __name__ == "__main__":
    main()
