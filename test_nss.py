"""Tests for Now Serving Seoul. Stdlib only, no network.

    python3 -m unittest test_nss
"""
import datetime as dt
import unittest

import nss_build as B
import nss_common as C
import nss_harvest as H


def row(mgt="1", name="부빔", t="한식", day="2026-10-08", state="01",
        road="서울특별시 용산구 서빙고로 137, 1층 (용산동6가)", lot="서울특별시 용산구 용산동6가 1", closed=""):
    return {"MGTNO": mgt, "BPLCNM": name, "UPTAENM": t, "APVPERMYMD": day,
            "TRDSTATEGBN": state, "RDNWHLADDR": road, "SITEWHLADDR": lot, "DCBYMD": closed}


class Services(unittest.TestCase):
    def test_jongno_is_jn_not_jungnang(self):
        self.assertEqual(C.DISTRICTS["JN"][1], "종로구")
        self.assertNotIn("JR", C.DISTRICTS)

    def test_sixteen_registers(self):
        self.assertEqual(len(C.services()), 16)


class Exclusion(unittest.TestCase):
    def test_ordinary_restaurant_is_listed(self):
        self.assertIsNone(C.exclusion(row()))

    def test_skipped_types(self):
        for t in ("편의점", "푸드트럭", "철도역구내", "백화점"):
            self.assertIsNotNone(C.exclusion(row(t=t)), t)

    def test_temporary_name(self):
        self.assertEqual(C.exclusion(row(name="야심떡카페(한시적)")), "temporary or pop-up")

    def test_food_hall_address(self):
        self.assertIsNotNone(C.exclusion(row(
            road="서울특별시 강남구 압구정로 343, 갤러리아백화점 지하1층 (압구정동)")))


class Names(unittest.TestCase):
    def test_bracketed_latin(self):
        self.assertEqual(C.english_name("사보서울(SAVO SEOUL)"), "SAVO SEOUL")

    def test_all_latin(self):
        self.assertEqual(C.english_name("Cafe Onion"), "Cafe Onion")

    def test_korean_only_is_none(self):
        self.assertIsNone(C.english_name("부빔"))

    def test_mixed_bracket_is_not_english(self):
        self.assertIsNone(C.english_name("이프유캔(성수)"))


class Addresses(unittest.TestCase):
    def test_dong_with_ga(self):
        self.assertEqual(C.neighborhood("서울특별시 용산구 서빙고로 137, 일대 (용산동6가)", ""), "용산동6가")

    def test_dong_before_building_name(self):
        self.assertEqual(C.neighborhood(
            "서울특별시 성동구 왕십리로 137, B127호 (성수동1가, 서울숲아이파크리버포레)", ""), "성수동1가")

    def test_lookup_strips_floor_and_dong(self):
        self.assertEqual(C.lookup_address("서울특별시 마포구 성미산로 161-11, White House 1층 (연남동)"),
                         "서울특별시 마포구 성미산로 161-11")

    def test_unknown_type_keeps_korean(self):
        self.assertEqual(C.type_info("새업태", "072405"), ("새업태", "cafe"))


class Blogs(unittest.TestCase):
    E = {"licensed": "2026-09-01", "road": "서울특별시 마포구 토정로 128, 4층 (상수동)", "dong": "상수동"}
    POST = {"url": "https://blog.naver.com/a/1", "posted": "2026-09-20", "title": "한강 토오베 (TOVE)",
            "snippet": "", "text": "서울 마포구 토정로 128 신상 찻집"}

    def test_good_verdict(self):
        import nss_blogs as N
        r = N.accept("x", self.E, [self.POST], {"post": self.POST["url"], "english": "TOVE",
                                               "about": "A tea house overlooking the Han"})
        self.assertEqual(r["opened"]["url"], self.POST["url"])
        self.assertEqual(r["english"], "TOVE")

    def test_post_before_licence_is_not_an_opening(self):
        import nss_blogs as N
        p = dict(self.POST, posted="2026-08-01")
        self.assertIsNone(N.accept("x", self.E, [p], {"post": p["url"]})["opened"])

    def test_post_not_naming_the_street_is_not_an_opening(self):
        import nss_blogs as N
        p = dict(self.POST, text="부산 해운대 신상 찻집")
        self.assertIsNone(N.accept("x", self.E, [p], {"post": p["url"]})["opened"])

    def test_url_not_returned_by_search_is_refused(self):
        import nss_blogs as N
        self.assertIsNone(N.accept("x", self.E, [self.POST], {"post": "https://evil.example/"})["opened"])

    def test_english_must_appear_in_a_post(self):
        import nss_blogs as N
        self.assertIsNone(N.accept("x", self.E, [self.POST], {"english": "Han River Tove Cafe"})["english"])


class ModelNames(unittest.TestCase):
    def test_only_asked_names_without_hangul(self):
        import nss_names as N
        got = N.accept(["벨리풀", "뎅뎅"], {"벨리풀": "Belly Full", "뎅뎅": "뎅뎅", "기타": "Other"})
        self.assertEqual(got, {"벨리풀": "Belly Full"})


class DisplayName(unittest.TestCase):
    def test_company_form_removed(self):
        self.assertEqual(C.display_name("주식회사 안목서초"), "안목서초")
        self.assertEqual(C.display_name("유동부치아바타(주)"), "유동부치아바타")
        self.assertEqual(C.display_name("부빔"), "부빔")


class CheckList(unittest.TestCase):
    def test_short_read_is_refused(self):
        self.assertIn("last good", H.check_list([row()] * 90, 100, "용산구"))

    def test_wrong_district_is_refused(self):
        rows = [row(road="서울특별시 중랑구 면목로 1", lot="서울특별시 중랑구 면목동 1")] * 10
        self.assertIn("not in 용산구", H.check_list(rows, None, "용산구"))

    def test_good_read_passes(self):
        self.assertIsNone(H.check_list([row()] * 100, 100, "용산구"))


class Merge(unittest.TestCase):
    def test_adds_new_operating_licence(self):
        lic = {}
        added, closed, unknown = H.merge(lic, [row()], "YS", "072404", "2026-10-10", "2026-09-01")
        self.assertEqual((added, closed), (1, 0))
        self.assertEqual(lic["1"]["type_en"], "Korean")

    def test_ignores_old_and_closed(self):
        lic = {}
        H.merge(lic, [row(mgt="a", day="2026-01-01"), row(mgt="b", state="03")],
                "YS", "072404", "2026-10-10", "2026-09-01")
        self.assertEqual(lic, {})

    def test_closes_a_tracked_licence(self):
        lic = {}
        H.merge(lic, [row()], "YS", "072404", "2026-10-09", "2026-09-01")
        _, closed, _ = H.merge(lic, [row(state="03", closed="2026-10-10")],
                               "YS", "072404", "2026-10-10", "2026-09-01")
        self.assertEqual(closed, 1)
        self.assertEqual(lic["1"]["closed"], "2026-10-10")

    def test_a_licence_missing_from_a_read_is_not_closed(self):
        lic = {}
        H.merge(lic, [row()], "YS", "072404", "2026-10-09", "2026-09-01")
        H.merge(lic, [], "YS", "072404", "2026-10-10", "2026-09-01")
        self.assertEqual(lic["1"]["status"], "licensed")

    def test_unknown_type_is_reported(self):
        _, _, unknown = H.merge({}, [row(t="새업태")], "YS", "072404", "2026-10-10", "2026-09-01")
        self.assertEqual(unknown, {"새업태"})


class HomeIntro(unittest.TestCase):
    def test_every_district_is_named(self):
        text = " ".join(B.HOME_INTRO)
        for name, _ in C.DISTRICTS.values():
            self.assertIn(name, text)
        self.assertIn(C.district_count(), text)


class Build(unittest.TestCase):
    def state(self):
        lic = {}
        H.merge(lic, [row(), row(mgt="2", name="팝업(한시적)"), row(mgt="3", name="다른집", day="2026-10-01")],
                "YS", "072404", "2026-10-10", "2026-09-01")
        lic["1"].update(lat=37.52, lon=126.98)
        return {"licences": lic}

    def test_excluded_are_not_listed(self):
        ids = {e["id"] for e in B.listed(self.state(), {}, {})}
        self.assertEqual(ids, {"1", "3"})

    def test_us_style_dates(self):
        self.assertEqual(B.day_text(dt.date(2026, 10, 8)), "Thursday, October 8")
        self.assertEqual(B.day_text(dt.date(2026, 10, 5), weekday=False, year=True), "October 5, 2026")

    def test_stamp(self):
        self.assertEqual(B.stamp_text("2026-10-10T18:02"), "October 10, 2026, 6:02 p.m.")
        self.assertEqual(B.stamp_text("2026-10-10T00:15"), "October 10, 2026, 12:15 a.m.")

    def test_entry_says_newly_licensed_and_escapes(self):
        e = B.listed(self.state(), {}, {})[0]
        e["name"] = "<b>"
        h = B.entry_html(e)
        self.assertIn("Newly licensed", h)
        self.assertIn("&lt;b&gt;", h)

    def test_same_place_twice_is_listed_once(self):
        lic = {}
        H.merge(lic, [row(mgt="a", name="초초맛차", road="서울특별시 중구 을지로 281 (을지로7가)", day="2026-10-08"),
                      row(mgt="b", name="초초맛차", road="서울특별시 중구 을지로 281, DDP 팔거리 (을지로7가)", day="2026-10-08")],
                "JG", "072405", "2026-10-10", "2026-09-01")
        self.assertEqual([e["id"] for e in B.listed({"licences": lic}, {}, {})], ["a"])

    def test_english_preference_blog_then_licence_then_model(self):
        st = self.state()
        st["licences"]["1"]["name_en"] = "LICENCE"
        e = [x for x in B.listed(st, {"부빔": "MODEL"}, {"1": {"english": "BLOG"}}) if x["id"] == "1"][0]
        self.assertEqual(e["name_en"], "BLOG")
        e = [x for x in B.listed(st, {"부빔": "MODEL"}, {}) if x["id"] == "1"][0]
        self.assertEqual(e["name_en"], "LICENCE")

    def test_points_only_pinned(self):
        self.assertEqual(len(B.points(B.listed(self.state(), {}, {}))), 1)

    def test_kakao_link_uses_coordinates(self):
        e = [x for x in B.listed(self.state(), {}, {}) if x["id"] == "1"][0]
        self.assertTrue(B.kakao_link(e).startswith("https://map.kakao.com/link/map/"))

    def test_points_json_cannot_close_the_script(self):
        st = self.state()
        st["licences"]["1"]["name"] = "</script><b>"
        html = B.page("t", "l", "", B.listed(st, {}, {}), "/")
        self.assertNotIn("</script><b>", html)


if __name__ == "__main__":
    unittest.main()
