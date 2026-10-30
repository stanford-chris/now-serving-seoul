"""Tests for Now Serving Seoul. Stdlib only, no network.

    python3 -m unittest test_nss
"""
import datetime as dt
import unittest

import nss_build as B
import nss_card as K
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

    def test_food_hall_in_the_name(self):
        self.assertIsNotNone(C.exclusion(row(name="사월에보리밥 청밀당 동대문현대아울렛점",
                                             road="서울특별시 중구 장충단로 13 (을지로6가)")))
        self.assertIsNotNone(C.exclusion(row(name="더정 우롱티프로젝트 AK플라자홍대점")))

    def test_shared_kitchen_is_delivery_only(self):
        self.assertEqual(C.exclusion(row(road="서울특별시 강남구 봉은사로29길 35, 지하2층 주방 24호 (논현동)")),
                         "delivery only")

    def test_convenience_store_by_chain_name(self):
        # Real names from the register, licensed as 기타 휴게음식점.
        for n in ("이마트24대치랜드마크점", "CU만리재옛길점", "씨유 논현대승점",
                  "지에스25  역삼허브", "세븐일레븐 공덕자이점", "GS25종로율곡로점"):
            self.assertEqual(C.exclusion(row(t="기타 휴게음식점", name=n)), "convenience store", n)

    def test_chain_name_only_at_the_start(self):
        for n in ("커비 Cubby", "Cucina 쿠치나", "카페 씨유어게인"):
            self.assertIsNone(C.exclusion(row(name=n)), n)

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
    def test_count_matches_the_districts(self):
        self.assertIn(f" {C.district_count()} districts", " ".join(B.HOME_INTRO))


class Build(unittest.TestCase):
    def state(self):
        lic = {}
        H.merge(lic, [row(), row(mgt="2", name="팝업(한시적)"), row(mgt="3", name="다른집", day="2026-10-01")],
                "YS", "072404", "2026-10-10", "2026-09-01")
        lic["1"].update(lat=37.52, lon=126.98)
        return {"licences": lic}

    def test_excluded_are_not_listed(self):
        ids = {e["id"] for e in B.listed(self.state(), {})}
        self.assertEqual(ids, {"1", "3"})

    def test_us_style_dates(self):
        self.assertEqual(B.day_text(dt.date(2026, 10, 8)), "Thursday, Oct. 8")
        self.assertEqual(B.day_text(dt.date(2026, 10, 5), weekday=False, year=True), "Oct. 5, 2026")
        self.assertEqual(B.day_text(dt.date(2026, 9, 28), weekday=False), "Sept. 28")
        self.assertEqual(B.day_text(dt.date(2026, 6, 3), weekday=False), "June 3")

    def test_stamp(self):
        self.assertEqual(B.stamp_text("2026-10-10T18:02"), "Oct. 10, 2026, 6:02 p.m.")
        self.assertEqual(B.stamp_text("2026-10-10T00:15"), "Oct. 10, 2026, 12:15 a.m.")

    def test_entry_says_newly_licensed_and_escapes(self):
        e = B.listed(self.state(), {})[0]
        e["name"] = "<b>"
        h = B.entry_html(e)
        self.assertIn("Newly licensed", h)
        self.assertIn("&lt;b&gt;", h)

    def test_same_place_twice_is_listed_once(self):
        lic = {}
        H.merge(lic, [row(mgt="a", name="초초맛차", road="서울특별시 중구 을지로 281 (을지로7가)", day="2026-10-08"),
                      row(mgt="b", name="초초맛차", road="서울특별시 중구 을지로 281, DDP 팔거리 (을지로7가)", day="2026-10-08")],
                "JG", "072405", "2026-10-10", "2026-09-01")
        self.assertEqual([e["id"] for e in B.listed({"licences": lic}, {})], ["a"])

    def test_english_preference_licence_then_model(self):
        st = self.state()
        st["licences"]["1"]["name_en"] = "LICENCE"
        e = [x for x in B.listed(st, {"부빔": "MODEL"}) if x["id"] == "1"][0]
        self.assertEqual(e["name_en"], "LICENCE")

    def test_kind_label_comes_from_types_not_the_stored_copy(self):
        st = self.state()
        st["licences"]["1"].update(type_ko="호프/통닭", type_en="Beer and chicken (hof)", group="bar")
        e = [x for x in B.listed(st, {}) if x["id"] == "1"][0]
        self.assertEqual((e["type_en"], e["group"]), ("Beer and chicken", "bar"))

    def closures(self):
        st = self.state()
        lic = st["licences"]
        lic["1"].update(status="closed", closed="2026-10-18",      # nothing else there
                        road="서울특별시 중구 을지로 99 (을지로3가)")
        lic["3"].update(status="closed", closed="2026-10-12",      # replaced: same address,
                        road="서울특별시 마포구 독막로 1 (상수동)")   # a later open licence
        lic["9"] = dict(lic["3"], status="licensed", name="새집", licensed="2026-10-05")
        lic["9"].pop("closed")
        return st

    def test_closures_only_on_the_site(self):
        st = self.closures()
        self.assertNotIn("1", {e["id"] for e in B.listed(st, {})})
        ids = {e["id"] for e in B.listed(st, {}, closed=True)}
        self.assertIn("1", ids)
        self.assertNotIn("3", ids, "a replaced licence is a re-licensing, not a closure")
        self.assertIn("9", ids)

    def test_closed_tag_and_no_map_dot(self):
        e = [x for x in B.listed(self.closures(), {}, closed=True) if x["id"] == "1"][0]
        h = B.entry_html(e)
        self.assertIn("Closed by Oct. 18", h)
        self.assertIn("is-closed", h)
        self.assertNotIn("Newly licensed", h)
        self.assertEqual(B.points([e]), [])

    def test_points_only_pinned(self):
        self.assertEqual(len(B.points(B.listed(self.state(), {}))), 1)

    def test_kakao_link_uses_coordinates(self):
        e = [x for x in B.listed(self.state(), {}) if x["id"] == "1"][0]
        self.assertTrue(B.kakao_link(e).startswith("https://map.kakao.com/link/map/"))

    def test_points_json_cannot_close_the_script(self):
        st = self.state()
        st["licences"]["1"]["name"] = "</script><b>"
        html = B.page("t", "l", "", B.listed(st, {}), "/")
        self.assertNotIn("</script><b>", html)


class KoreanShown(unittest.TestCase):
    def test_bracketed_english_already_shown_is_dropped(self):
        self.assertEqual(B.korean_shown("얌얌닭발(YamYam)", "YamYam"), "얌얌닭발")
        self.assertEqual(B.korean_shown("엘(L)", "L"), "엘")
        self.assertEqual(B.korean_shown("위스위츠 아카이브 (we sweets archive)", "We Sweets Archive"),
                         "위스위츠 아카이브")

    def test_kept_when_the_english_shown_says_something_else(self):
        self.assertEqual(B.korean_shown("엘(L)", "Elle Bistro"), "엘(L)")
        self.assertEqual(B.korean_shown("가게(2층)", "Gage"), "가게(2층)")    # no Latin in it
        self.assertEqual(B.korean_shown("(L)", "L"), "(L)")                  # nothing left
        self.assertEqual(B.korean_shown("부빔", None), "부빔")


class TitleGloss(unittest.TestCase):
    def test_his_examples(self):
        self.assertEqual(B.title_gloss("Matsarang (love of flavor)"), "Matsarang (Love of Flavor)")
        self.assertEqual(B.title_gloss("Dalkom Table (sweet table)"), "Dalkom Table (Sweet Table)")

    def test_capitals_only_added(self):
        self.assertEqual(B.title_gloss("Yun Sikdang (Yun's restaurant)"), "Yun Sikdang (Yun's Restaurant)")
        self.assertEqual(B.title_gloss("X (NH Nonghyup Tower, 14th floor)"),
                         "X (NH Nonghyup Tower, 14th Floor)")

    def test_hyphens_semicolons_and_minor_words(self):
        self.assertEqual(B.title_gloss("Geobugi (turtle; charcoal-grilled eel)"),
                         "Geobugi (Turtle; Charcoal-Grilled Eel)")
        self.assertEqual(B.title_gloss("Uju Dak Hof (chicken and beer)"), "Uju Dak Hof (Chicken and Beer)")
        self.assertEqual(B.title_gloss("Ka (a place to sit in)"), "Ka (A Place to Sit In)")

    def test_a_bracket_mid_name_and_none(self):
        self.assertEqual(B.title_gloss("Garam Guksi (noodles), Nonhyeon branch"),
                         "Garam Guksi (Noodles), Nonhyeon branch")
        self.assertEqual(B.title_gloss("Hey Jude"), "Hey Jude")
        self.assertIsNone(B.title_gloss(None))


def place(name="부빔", en="Bubim", group="restaurant", district="YS", day="2026-10-26",
          type_en="Korean"):
    return {"name": name, "name_ko": name, "name_en": en, "group": group, "district": district,
            "date": dt.date.fromisoformat(day), "type_en": type_en}


class Card(unittest.TestCase):
    def test_newest_day_waits_for_a_later_one(self):
        es = [place(day="2026-10-23"), place(day="2026-10-26"), place(day="2026-10-27")]
        self.assertEqual(K.complete_days(es), [dt.date(2026, 10, 23), dt.date(2026, 10, 26)])
        self.assertEqual(K.next_day(es, set()), dt.date(2026, 10, 26))

    def test_a_posted_day_is_not_posted_again(self):
        es = [place(day="2026-10-23"), place(day="2026-10-26"), place(day="2026-10-27")]
        self.assertIsNone(K.next_day(es, {"2026-10-26"}))

    def test_never_goes_back_to_an_older_unposted_day(self):
        es = [place(day="2026-10-21"), place(day="2026-10-23"), place(day="2026-10-26"),
              place(day="2026-10-27")]
        # Oct. 21 posted, Oct. 23 missed: the next post is Oct. 26, never Oct. 23.
        self.assertEqual(K.next_day(es, {"2026-10-21"}), dt.date(2026, 10, 26))
        self.assertIsNone(K.next_day(es, {"2026-10-21", "2026-10-26"}))

    def test_one_day_on_record_posts_nothing(self):
        self.assertIsNone(K.next_day([place()], set()))

    def test_independents_before_branches(self):
        es = [place("세븐일레븐 르네스퀘어점", "7-Eleven, Reune Square branch"),
              place("아띠몽", "Attimong", district="MP"),
              place("도손", "Doson", district="JG")]
        names = [e["name_en"] for e in K.highlights(es, n=3)]
        self.assertEqual(names, ["Attimong", "Doson", "7-Eleven, Reune Square branch"])

    def test_highlights_spread_across_kinds(self):
        es = [place(f"식당{i}", f"R{i}") for i in range(4)] + [place("바", "Zed", group="bar")]
        groups = [e["group"] for e in K.highlights(es, n=2)]
        self.assertEqual(sorted(groups), ["bar", "restaurant"])

    def test_card_name_drops_a_trailing_gloss_only(self):
        self.assertEqual(K.card_name("Susu Gimbap (seaweed rice rolls)"), "Susu Gimbap")
        self.assertEqual(K.card_name("L (Bar) House"), "L (Bar) House")
        self.assertEqual(K.card_name(None), "")

    def test_cuisines_keep_their_capital(self):
        self.assertEqual(K.kind_text("Chinese"), "Chinese")
        self.assertEqual(K.kind_text("Café or snack bar"), "café or snack bar")

    def test_alt_text_lists_every_place(self):
        es = [place(f"식당{i}", f"R{i}") for i in range(12)]
        alt = K.alt_text(dt.date(2026, 10, 26), es)
        self.assertTrue(all(f"R{i} (식당{i})" in alt for i in range(12)))
        self.assertIn("12 new food licenses on Monday, Oct. 26", alt)

    def test_map_keeps_every_place_of_the_day_in_frame(self):
        backdrop = [{"lon": 126.95 + i / 1000, "lat": 37.52 + i / 2000} for i in range(200)]
        far = (127.30, 37.40)            # a place well outside the backdrop
        to_xy, height = K.project([(b["lon"], b["lat"]) for b in backdrop], keep=[far])
        x, y = to_xy(*far)
        self.assertTrue(0 <= x <= K.MAP_WIDTH and 0 <= y <= height)

    def test_map_frame_ignores_stray_backdrop_dots(self):
        pts = [(126.95 + i / 1000, 37.52) for i in range(200)] + [(127.9, 37.52)]
        to_xy, _ = K.project(pts)
        self.assertGreater(to_xy(127.9, 37.52)[0], K.MAP_WIDTH)

    def test_map_alt_names_each_district_count(self):
        es = [place(district="GN"), place(district="GN"), place(district="MP")]
        alt = K.map_alt(dt.date(2026, 10, 26), es)
        self.assertIn("Gangnam 2, Mapo 1", alt)

    def test_handle_proof_is_the_did_alone(self):
        self.assertRegex(C.BLUESKY_DID, r"^did:plc:[a-z2-7]{24}$")

    def test_headline_singular(self):
        self.assertEqual(K.headline(1), "1 new food license")



class InterestBox(unittest.TestCase):
    """The email-interest counter: every district offered, no address field."""

    def test_every_district_and_all(self):
        h = B.interest_html()
        for k in C.DISTRICTS:
            self.assertIn(f'value="{k}"', h)
        self.assertIn('value="ALL"', h)

    def test_counter_asks_for_no_email(self):
        # The address goes only to Buttondown's form, never to the counter's.
        h = B.interest_html()
        counter = h[h.index('<form id="interest"'):h.index("</form>")]
        self.assertNotIn('type="email"', counter)
        self.assertIn("The count keeps no email address", h)

    def test_waitlist_posts_to_buttondown(self):
        h = B.interest_html()
        self.assertIn('action="https://buttondown.com/api/emails/embed-subscribe/nowservingseoul"', h)
        self.assertIn('name="email"', h)
        self.assertIn("kept by Buttondown", h)

    def test_weekly_is_the_default(self):
        self.assertIn('value="weekly" checked', B.interest_html())

    def test_only_on_pages_that_ask(self):
        with_box = B.page("t", "l", "", [], "/x/", with_map=False, with_filters=False, interest=True)
        without = B.page("t", "l", "", [], "/x/", with_map=False, with_filters=False)
        self.assertIn('class="interest"', with_box)
        self.assertIn("/api/interest", with_box)
        self.assertNotIn('class="interest"', without)


if __name__ == "__main__":
    unittest.main()
