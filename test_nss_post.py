"""Tests for nss_post.py with a fake Bluesky client: no network, no Chrome.

    python3 -m unittest test_nss_post
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import nss_post as P


def lic(day, district="YS", group="restaurant", n=0):
    return {"district": district, "dong": "", "excluded": None, "first_seen": "2026-10-28",
            "group": group, "lat": 37.53 + n / 1000, "lon": 126.99 + n / 1000, "licensed": day,
            "lot": f"서울특별시 용산구 {n}", "name": f"가게{day}{n}", "name_en": f"Shop {n}",
            "register": "072404", "road": f"서울특별시 용산구 길 {day} {n}", "status": "licensed",
            "type_en": "Korean", "type_ko": "한식"}


class FakeRes:
    def __init__(self, uri):
        self.uri, self.cid = uri, "cid"


class FakeClient:
    def __init__(self, fail_reply=False):
        self.posts, self.fail_reply = [], fail_reply

    def upload_blob(self, data):
        # A real BlobRef: atproto's Image model refuses anything else, and a
        # mock here fails inside the embed, not where the mistake is.
        from atproto_client.models.blob_ref import BlobRef, IpldLink
        return mock.Mock(blob=BlobRef(mime_type="image/png", size=len(data),
                                      ref=IpldLink(link="bafkreie5737gdxlw5i64vzichcalba3z2v5n6icifvx5xytvske7mr3hpm")))

    def send_post(self, text, embed=None, langs=None, reply_to=None):
        if reply_to is not None and self.fail_reply:
            raise RuntimeError("network went away")
        self.posts.append({"text": text, "reply": reply_to is not None})
        return FakeRes(f"at://post/{len(self.posts)}")


def fake_render(page, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), "white").save(out)
    return out, (40, 30)


class Post(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        licences = {f"{d}-{n}": lic(d, n=n) for d in ("2026-10-23", "2026-10-26", "2026-10-27")
                    for n in range(3)}
        (self.tmp / "licences.json").write_text(json.dumps({"licences": licences}))
        self.patches = [mock.patch.object(P, "STATE", self.tmp / "licences.json"),
                        mock.patch.object(P, "POST_STATE", self.tmp / "post_state.json"),
                        mock.patch.object(P.K, "render", fake_render),
                        mock.patch.object(P.K, "DRAFTS", self.tmp / "drafts"),
                        mock.patch.object(P.b, "load", lambda path: {}),
                        mock.patch("builtins.print")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def run_main(self, *argv, client=None):
        with mock.patch("sys.argv", ["nss_post.py", *argv]), \
             mock.patch.object(P, "login", lambda: client):
            P.main()

    def test_posts_the_card_then_the_map_as_a_reply(self):
        c = FakeClient()
        self.run_main(client=c)
        self.assertEqual([p["reply"] for p in c.posts], [False, True])
        self.assertIn("Monday, Oct. 26", c.posts[0]["text"].build_text())
        facets = [f.features[0] for f in c.posts[0]["text"].build_facets()]
        self.assertEqual(facets[0].uri, "https://nowservingseoul.com/")
        self.assertEqual([f.tag for f in facets[1:]], ["Seoul", "FoodSky"])
        self.assertTrue(c.posts[0]["text"].build_text().endswith("\n#Seoul #FoodSky"))
        state = json.loads(P.POST_STATE.read_text())["posted"]
        self.assertEqual(state["2026-10-26"]["uri"], "at://post/1")
        self.assertEqual(state["2026-10-26"]["map_uri"], "at://post/2")

    def test_a_second_run_posts_nothing(self):
        self.run_main(client=FakeClient())
        c = FakeClient()
        self.run_main(client=c)
        self.assertEqual(c.posts, [])

    def test_failed_reply_keeps_the_card_recorded_and_exits_1(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main(client=FakeClient(fail_reply=True))
        self.assertEqual(cm.exception.code, 1)
        state = json.loads(P.POST_STATE.read_text())["posted"]
        self.assertIn("uri", state["2026-10-26"])
        c = FakeClient()
        self.run_main(client=c)            # the next run does not post the card again
        self.assertEqual(c.posts, [])

    def test_dry_run_signs_in_to_nothing_and_saves_nothing(self):
        with mock.patch.object(P, "login", side_effect=AssertionError("signed in")), \
             mock.patch("sys.argv", ["nss_post.py", "--dry-run"]):
            P.main()
        self.assertFalse(P.POST_STATE.exists())

    def test_oversized_png_goes_as_jpeg(self):
        big = self.tmp / "big.png"
        Image.effect_noise((900, 900), 120).convert("RGB").save(big)
        self.assertGreater(big.stat().st_size, P.MAX_BLOB)
        data = P.image_bytes(big)
        self.assertLessEqual(len(data), P.MAX_BLOB)
        self.assertEqual(data[:2], b"\xff\xd8")


if __name__ == "__main__":
    unittest.main()
