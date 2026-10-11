#!/usr/bin/env python3
"""The weekly blog pass: which newly licensed places a Naver blog post says
have opened, and the English name a post gives them.

    python3 nss_blogs.py                 # check up to MAX_PLACES places
    python3 nss_blogs.py --limit 10      # a small run
    python3 nss_blogs.py --dry-run       # search and judge, write nothing

For each listed place licensed in the last LOOKBACK_DAYS days, not yet marked
opened and not checked in the last RECHECK_DAYS days: one Naver blog search for
its name and 동, the posts that name it read in full, and Fable asked, a few
places at a time, whether a post is about THIS place (same name, same street)
and says it has opened. Results in data/blogs.json, keyed by management
number:

    {"checked": "2026-10-10", "opened": {"url", "posted", "title"} | null,
     "english": "Belly Full" | null, "about": "one line in our words" | null}

A place a post shows is delivery-only (a delivery kitchen, a shop-in-shop
kitchen) is dropped from the site, his call of 11 October 2026. A post by the
business itself counts as evidence of an opening, his call the same day.

Rules that stop a wrong "opened":
- the post must be one the search returned, dated on or after the licence
  (a post from before it is about an earlier place), and must itself name the
  licence's road or 동, whatever the model says;
- "about" is written by the model in its own words and capped; post text is
  never stored or shown, only linked;
- a place the model is unsure of is left "newly licensed".

Naver is read with curl and a browser User-Agent (the route ~/Scripts/
seoul_weekly.py uses); searches are spaced SEARCH_SPACING apart and a page
that loads but cannot be parsed stops the run as NOT CHECKED, so a changed
layout never reads as "no posts".

Exit 0 done, 1 a model batch failed (those places are retried next run),
2 Naver could not be read.
"""
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import quote
from zoneinfo import ZoneInfo

from nss_common import DATA, STATE, display_name, lookup_address
from nss_model import HANGUL, ask

SEOUL = ZoneInfo("Asia/Seoul")
BLOGS = DATA / "blogs.json"
LOOKBACK_DAYS = 42
RECHECK_DAYS = 6
MAX_PLACES = 200
SEARCH_SPACING = 2.5
POSTS_PER_PLACE = 3
TEXT_CHARS = 2500
JUDGE_BATCH = 6
ABOUT_MAX = 120

NAVER_SEARCH = ("https://search.naver.com/search.naver?ssc=tab.blog.all"
                "&query={q}&sm=tab_opt&nso=so:dd,p:{period}")
DESK_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
           "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TAG_RE = re.compile(r"<[^>]+>")


class NaverUnreadable(RuntimeError):
    pass


def curl(url, ua):
    r = subprocess.run(["curl", "-sL", "--compressed", "--max-time", "30", "-A", ua, url],
                       capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"curl exit {r.returncode} for {url[:80]}")
    return r.stdout


def plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", fragment))).strip()


def naver_age(label, today):
    """'3시간 전', '2일 전', '어제', '2026.10.05.' -> ISO date, or None."""
    label = label.strip()
    if m := re.match(r"(\d{4})\.\s?(\d{1,2})\.\s?(\d{1,2})", label):
        return dt.date(*map(int, m.groups())).isoformat()
    if "분 전" in label or "시간 전" in label or label == "방금 전":
        return today.isoformat()
    if label == "어제":
        return (today - dt.timedelta(days=1)).isoformat()
    if m := re.match(r"(\d+)일 전", label):
        return (today - dt.timedelta(days=int(m.group(1)))).isoformat()
    if m := re.match(r"(\d+)주 전", label):
        return (today - dt.timedelta(weeks=int(m.group(1)))).isoformat()
    return None


def parse_results(page, today):
    """Posts on a Naver blog search page. Copied from seoul_weekly.py's
    naver_search(). Raises NaverUnreadable when the page carries neither a
    result nor Naver's own "no results" notice."""
    out = []
    for it in page.split('data-template-id="ugcItem"')[1:]:
        link = re.search(r'href="(https://blog\.naver\.com/[A-Za-z0-9_.-]+/\d+)"[^>]*>'
                         r'<span[^>]*text-type-headline1[^>]*>(.*?)</span>', it, re.S)
        if not link:
            continue
        age = re.search(r'profile-info-subtext">([^<]+)<', it)
        snip = re.search(r'fds-ugc-ellipsis\d?"[^>]*>(.*?)</a>', it, re.S)
        out.append({"title": plain(link.group(2)), "url": link.group(1),
                    "posted": naver_age(age.group(1), today) if age else None,
                    "snippet": plain(snip.group(1)) if snip else ""})
    if not out and "ugcItem" not in page and "검색결과가 없습니다" not in page:
        raise NaverUnreadable("Naver search page loaded but no results could be parsed")
    return out


def post_text(url):
    page = curl(url.replace("://blog.", "://m.blog."), MOBILE_UA)
    paras = re.findall(r'<p class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>', page, re.S)
    return plain(" ".join(paras))


def squash(s):
    return re.sub(r"\s+", "", s or "")


def names_place(post, name):
    """A post counts only if its title or snippet carries the place's name."""
    n = squash(name)
    return n and (n in squash(post["title"]) or n in squash(post["snippet"]))


def query_for(e):
    dong = re.sub(r"\d+가$|\d+동$", "", e.get("dong") or "").strip()
    return f"{display_name(e['name'])} {dong}".strip()


JUDGE_PROMPT = """You are checking whether new restaurants, bars and cafés in Seoul have opened, using Korean blog posts. Each place below comes from a food license: its name, street address and license date, followed by blog posts whose title or summary mention the name.

For each place, decide:
- "post": the URL of a post that is clearly about THIS place (same name AND the same street or neighborhood) and shows it is open (the writer visited, or it announces the opening), else null. If posts disagree or the location is unclear, use null.
- "english": the place's English name ONLY if a post writes it in Latin letters as the place's own name (signage, menu, logo, Instagram handle), else null. Do not translate or romanize yourself.
- "delivery_only": true if a post shows the place is delivery or takeout-only with nowhere to eat or drink in (a delivery kitchen, a shared "shop-in-shop" kitchen), else false.
- "about": if "post" is not null, one short sentence in plain English, your own words, saying what the place serves (for example "A bakery known for salt bread"), at most 15 words, no quotation from the post; else null.

Reply with JSON only: {"<place id>": {"post": ..., "english": ..., "about": ...}}.

"""


def judge(batch):
    """batch: [(id, entry, posts)] -> {id: verdict}."""
    lines = []
    for pid, e, posts in batch:
        lines.append(f"PLACE {pid}: {display_name(e['name'])} | {e['road'] or e['lot']} | "
                     f"licensed {e['licensed']}")
        for p in posts:
            lines.append(f"  POST {p['url']} | posted {p['posted']} | {p['title']} | "
                         f"{p.get('text') or p['snippet']}")
    return ask(JUDGE_PROMPT + "\n".join(lines))


def place_words(e):
    """Words a post about this place should contain: the road name from the
    road address and the 동 without its number. "서울특별시 마포구 토정로 128,
    ... (상수동)" -> {"토정로", "상수"}."""
    words = set()
    m = re.search(r"[구]\s+(\S+(?:로|길))\s", e.get("road") or "")
    if m:
        words.add(m.group(1))
    dong = re.sub(r"\d*(동|가)$", "", re.sub(r"\d+가$", "", e.get("dong") or ""))
    if len(dong) >= 2:
        words.add(dong)
    return words


def located(e, post):
    """The model may not mark a post as this place unless the post itself
    names the street or the 동. Pure, for tests."""
    blob = squash(post["title"] + post.get("text", "") + post["snippet"])
    return any(squash(w) in blob for w in place_words(e))


def accept(pid, e, posts, verdict):
    """Validate one verdict. Pure, for tests."""
    out = {"opened": None, "english": None, "about": None, "delivery_only": False}
    if not isinstance(verdict, dict):
        return out
    out["delivery_only"] = verdict.get("delivery_only") is True
    by_url = {p["url"]: p for p in posts}
    p = by_url.get(verdict.get("post"))
    if p and p.get("posted") and p["posted"] >= e["licensed"] and located(e, p):
        about = verdict.get("about")
        out["opened"] = {"url": p["url"], "posted": p["posted"], "title": p["title"]}
        if isinstance(about, str) and about.strip() and not HANGUL.search(about):
            out["about"] = about.strip()[:ABOUT_MAX]
    en = verdict.get("english")
    if (isinstance(en, str) and en.strip() and not HANGUL.search(en) and len(en) <= 80
            and any(en.strip().lower() in (q["title"] + " " + q.get("text", "") + " " + q["snippet"]).lower()
                    for q in posts)):
        out["english"] = en.strip()
    return out


def due(state, blogs, today):
    floor = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    recheck = (today - dt.timedelta(days=RECHECK_DAYS)).isoformat()
    out = []
    for mgt, e in state["licences"].items():
        if e.get("excluded") or e.get("status") == "closed" or e["licensed"] < floor:
            continue
        b = blogs.get(mgt, {})
        if b.get("opened") or b.get("checked", "") > recheck:
            continue
        out.append((mgt, e))
    out.sort(key=lambda x: x[1]["licensed"])   # oldest first: most likely to have posts
    return out


def main(argv):
    dry = "--dry-run" in argv
    limit = MAX_PLACES
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    state = json.loads(STATE.read_text())
    try:
        blogs = json.loads(BLOGS.read_text())
    except FileNotFoundError:
        blogs = {}
    today = dt.datetime.now(SEOUL).date()
    places = due(state, blogs, today)[:limit]
    print(f"{len(places)} places to check")
    found, rc = [], 0
    for mgt, e in places:
        q = query_for(e)
        try:
            page = curl(NAVER_SEARCH.format(q=quote(q), period="1m"), DESK_UA)
            posts = [p for p in parse_results(page, today) if names_place(p, display_name(e["name"]))]
        except NaverUnreadable as ex:
            print(f"NOT CHECKED: {ex} (query {q})")
            rc = 2
            break
        except RuntimeError as ex:
            print(f"  search failed for {q}: {ex}")
            continue
        posts = posts[:POSTS_PER_PLACE]
        for p in posts:
            try:
                p["text"] = post_text(p["url"])[:TEXT_CHARS]
            except RuntimeError:
                pass
            time.sleep(SEARCH_SPACING / 2)
        found.append((mgt, e, posts))
        time.sleep(SEARCH_SPACING)

    with_posts = [f for f in found if f[2]]
    print(f"{len(found)} searched, {len(with_posts)} with posts naming the place")
    results = {mgt: {"opened": None, "english": None, "about": None, "delivery_only": False}
               for mgt, _, posts in found
               if not posts}
    for i in range(0, len(with_posts), JUDGE_BATCH):
        batch = with_posts[i:i + JUDGE_BATCH]
        try:
            verdicts = judge(batch)
        except RuntimeError as ex:
            print(f"  judging failed: {ex}")
            rc = max(rc, 1)
            continue
        for mgt, e, posts in batch:
            results[mgt] = accept(mgt, e, posts, verdicts.get(mgt))
    opened = sum(1 for r in results.values() if r["opened"])
    english = sum(1 for r in results.values() if r["english"])
    print(f"opened {opened}, English names {english}")
    for mgt, r in results.items():
        if r["opened"] or r["english"]:
            e = state["licences"][mgt]
            print(f"  {display_name(e['name'])}: {r['english'] or ''} {r['opened']['url'] if r['opened'] else ''}")
    if not dry:
        for mgt, r in results.items():
            blogs[mgt] = dict(r, checked=today.isoformat())
        tmp = BLOGS.with_suffix(".tmp")
        tmp.write_text(json.dumps(blogs, ensure_ascii=False, indent=1, sort_keys=True))
        os.replace(tmp, BLOGS)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
