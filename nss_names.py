#!/usr/bin/env python3
"""English names for listed places, from Sonnet, cached in data/names.json.

    python3 nss_names.py            # translate names not yet cached
    python3 nss_names.py --dry-run  # say how many, call nothing

The site shows, in this order of preference: the English the licence itself
carries in brackets, then this. Each Korean name is sent once, ever; the cache is the record.

The model is Fable 5.1, chosen 10 October 2026 on the same 20 real names:
Haiku gave "Deojeong" and "Peuricheu" where Sonnet gave "The Jeong" and
"Fritz", and Fable alone also recovered "Starlit" and "Firstier" and read
제비 as the bird. None recognized every English word spelled in Hangul
("벨리풀", probably Belly Full); a blog post's English used to correct those,
until the Naver blog pass was retired on 30 October 2026.

Exit 0 done, 1 a batch failed (those names stay Korean-only and are retried).
"""
import json
import os
import sys

from nss_common import DATA, STATE, display_name
from nss_model import HANGUL, ask

NAMES = DATA / "names.json"
BATCH = 40

PROMPT = """These are names of new restaurants, bars and cafés in Seoul, as written on their food licenses. For each, give the name an English-speaking visitor should see, following these rules:
- If the name is a Korean spelling of an English or other foreign word ("폴브레드"), give that word in its usual spelling ("Pol Bread"). If unsure of the exact spelling, romanize instead.
- Otherwise romanize it in Revised Romanization, with spaces between words and capitals as for a name ("육개장인" -> "Yukgaejangin").
- A branch suffix like "망원점" becomes ", Mangwon branch"; "본점" becomes ", main branch".
- Add a short meaning in parentheses ONLY when the name is ordinary Korean words a visitor would want explained, e.g. "Yukgaejangin (spicy beef soup)". Never explain a brand or invented word.
- Never guess facts about the place.
Reply with JSON only: {"<korean name>": "<english>"}.
"""


def wanted(state, cache):
    names = set()
    for e in state["licences"].values():
        if e.get("excluded") or e.get("status") == "closed" or e.get("name_en"):
            continue
        n = display_name(e["name"])
        if HANGUL.search(n) and n not in cache:
            names.add(n)
    return sorted(names)


def accept(batch, reply):
    """Only an answer for a name we asked about, with no Hangul left in it."""
    return {k: v.strip() for k, v in reply.items()
            if k in batch and isinstance(v, str) and v.strip() and not HANGUL.search(v)
            and len(v) <= 160}


def main(argv):
    dry = "--dry-run" in argv
    if [a for a in argv if a != "--dry-run"]:
        sys.exit(f"unknown arguments: {argv}")
    state = json.loads(STATE.read_text())
    try:
        cache = json.loads(NAMES.read_text())
    except FileNotFoundError:
        cache = {}
    todo = wanted(state, cache)
    print(f"{len(todo)} names to translate, {len(cache)} cached")
    if dry or not todo:
        return 0
    rc = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            got = accept(batch, ask(PROMPT + json.dumps(batch, ensure_ascii=False)))
        except RuntimeError as e:
            print(f"  batch {i // BATCH + 1} failed: {e}")
            rc = 1
            continue
        cache.update(got)
        missing = len(batch) - len(got)
        print(f"  batch {i // BATCH + 1}: {len(got)} named" + (f", {missing} left Korean" if missing else ""))
        tmp = NAMES.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
        os.replace(tmp, NAMES)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
