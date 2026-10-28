#!/usr/bin/env python3
"""Now Serving Seoul: post the daily digest to Bluesky.

    python3 nss_post.py --dry-run      # render and print, sign in to nothing, post nothing
    python3 nss_post.py                # post the next day, if there is one

A thread of two: the card (nss_card.build_html) with the post text and a link
to the site, then the map as a reply. The day is nss_card.next_day(): the
newest licence date with a later one on record, and only if it is later than
every day already posted. No such day is a quiet run and exits 0.

State is data/post_state.json, {"posted": {"2026-10-26": {"uri", "map_uri",
"at"}}}. It is saved the moment the card posts, before the reply, so a failed
reply can never make the next run post the card again; the failure is logged
and the run exits 1.

Signs in by the account's DID, not its handle: the handle is changing from
nowservingseoul.bsky.social to nowservingseoul.com, and a DID sign-in works
on either side of that (checked 29 October 2026). Only the sign-in retries,
because a send that fails cannot tell a post that never landed from one whose
answer was lost, and retrying the second double-posts.
"""
import argparse
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

import nss_build as b
import nss_card as K
from nss_common import DATA, DISTRICTS, STATE

POST_STATE = DATA / "post_state.json"
DID = "did:plc:gnx7l3efyksa767sxgxhxlfn"
KEYCHAIN = ("nowservingseoul-bluesky", "nowservingseoul.com")    # service, account
MAX_BLOB = 950_000        # Bluesky refuses an image blob over about 976 KB
MAP_REPLY_TEXT = "Where they are, by district."


def load_posted():
    try:
        return json.loads(POST_STATE.read_text()).get("posted", {})
    except FileNotFoundError:
        return {}


def save_posted(posted):
    tmp = POST_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"posted": posted}, indent=1, sort_keys=True))
    os.replace(tmp, POST_STATE)


def image_bytes(path):
    """The PNG as rendered, or a JPEG of it if the PNG is over Bluesky's limit."""
    data = path.read_bytes()
    if len(data) <= MAX_BLOB:
        return data
    buf = io.BytesIO()
    Image.open(path).convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
    if buf.tell() > MAX_BLOB:
        raise RuntimeError(f"{path.name} is {buf.tell():,} bytes even as a JPEG")
    return buf.getvalue()


def card_text(day, es):
    """The post text as a TextBuilder: the site name is a link."""
    from atproto import client_utils
    text = K.post_text(day, es)
    head, site = text.rsplit(K.SITE, 1)[0], K.SITE
    return client_utils.TextBuilder().text(head).link(site, f"https://{site}/")


def login(retries=4):
    from atproto import Client, exceptions
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN[0],
                        "-a", KEYCHAIN[1], "-w"], capture_output=True, text=True)
    password = r.stdout.strip()
    if r.returncode or not password:
        sys.exit(f"no Bluesky app password in the Keychain ({KEYCHAIN[0]})")
    last = None
    for attempt in range(retries):
        try:
            client = Client()
            client.login(DID, password)
            return client
        except exceptions.NetworkError as exc:
            last = f"{type(exc).__name__}: {exc}"
            print(f"sign-in attempt {attempt + 1}/{retries} failed ({last})")
            time.sleep(2 * (attempt + 1))
    sys.exit(f"could not sign in after {retries} attempts: {last}")


def embed(client, data, alt, size):
    from atproto import models
    blob = client.upload_blob(data).blob
    return models.AppBskyEmbedImages.Main(images=[models.AppBskyEmbedImages.Image(
        image=blob, alt=alt,
        aspect_ratio=models.AppBskyEmbedDefs.AspectRatio(width=size[0], height=size[1]))])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="render and print; no sign-in, no post, no state")
    args = ap.parse_args()

    state = json.loads(STATE.read_text())
    entries = b.listed(state)
    if not entries:
        sys.exit("no listed licences: a failed harvest, not a quiet city")
    posted = load_posted()
    day = K.next_day(entries, posted)
    if day is None:
        print("nothing to post: no complete day later than the last one posted")
        return
    es = K.by_day(entries)[day]
    backdrop = [e for e in state["licences"].values()
                if "lat" in e and not e.get("excluded") and e["district"] in DISTRICTS]

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(args.dry_run and K.DRAFTS or tmp)
        card, card_size = K.render(K.build_html(day, es), out / f"{day}.png")
        mapp, map_size = K.render(K.map_html(day, es, backdrop), out / f"{day}-map.png")
        card_data, map_data = image_bytes(card), image_bytes(mapp)
        alt, map_alt = K.alt_text(day, es), K.map_alt(day, es)

        print(f"day: {b.day_text(day, year=True)} ({len(es)} places)")
        print(f"card {card_size[0]}x{card_size[1]}, {len(card_data):,} bytes; "
              f"map {map_size[0]}x{map_size[1]}, {len(map_data):,} bytes")
        print(f"post: {K.post_text(day, es)}\nreply: {MAP_REPLY_TEXT}")
        if args.dry_run:
            print(f"dry run: images in {out}, nothing posted, state unchanged")
            return

        from atproto import models
        client = login()
        res = client.send_post(text=card_text(day, es), embed=embed(client, card_data, alt, card_size),
                               langs=["en"])
        posted[day.isoformat()] = {"uri": res.uri,
                                   "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        save_posted(posted)
        print(f"posted {res.uri}")
        try:
            ref = models.create_strong_ref(res)
            reply = client.send_post(text=MAP_REPLY_TEXT, langs=["en"],
                                     reply_to=models.AppBskyFeedPost.ReplyRef(parent=ref, root=ref),
                                     embed=embed(client, map_data, map_alt, map_size))
        except Exception as exc:          # the card is up and recorded; say so and fail
            print(f"!! map reply failed: {type(exc).__name__}: {exc}")
            sys.exit(1)
        posted[day.isoformat()]["map_uri"] = reply.uri
        save_posted(posted)
        print(f"replied {reply.uri}")


if __name__ == "__main__":
    main()
