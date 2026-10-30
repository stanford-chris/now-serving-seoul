"""Now Serving Seoul: what the harvester and the site builder share.

The source is Seoul's food-licence register (지방행정 인허가 데이터, published
per district on data.seoul.go.kr under 공공누리 Type 1: credit the source,
commercial use and changes allowed). Two registers per district:
일반음식점 (072404, restaurants and most bars) and 휴게음식점 (072405, cafés,
bakeries, snack counters).
"""
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PUBLIC = HERE / "public"
STATE = DATA / "licences.json"
# The Bluesky account's DID. The site serves it at /.well-known/atproto-did,
# which is what proves the handle @nowservingseoul.com (his choice over a DNS
# record, 29 October 2026); nss_post.py signs in with it.
BLUESKY_DID = "did:plc:gnx7l3efyksa767sxgxhxlfn"

API = "http://openapi.seoul.go.kr:8088/{key}/json/{svc}/{a}/{b}/"
KEYCHAIN = ("seoul-open-data", "openapi.seoul.go.kr")    # service, account

# ⚠️ The suffix is NOT always the obvious one: `_JR` is Jungnang-gu (중랑구),
# not Jongno; Jongno is `_JN`. Found 10 October 2026, when every one of
# `_JR`'s 17,652 rows turned out to be in 중랑구. `ADDRESS_DISTRICT` is what
# the harvester checks each list against, so a wrong suffix fails loudly.
DISTRICTS = {
    "GN": ("Gangnam", "강남구"),
    "JG": ("Jung", "중구"),
    "JN": ("Jongno", "종로구"),
    "MP": ("Mapo", "마포구"),
    "SC": ("Seocho", "서초구"),
    "SD": ("Seongdong", "성동구"),
    "SP": ("Songpa", "송파구"),   # added 10 October 2026, his call, after the 25-district count
    "YS": ("Yongsan", "용산구"),
}
# The neighborhoods each district is on the list for, named on the About page.
NEIGHBORHOODS = {
    "GN": "Apgujeong, Cheongdam, Sinsa-dong and Garosu-gil",
    "JN": "Ikseon-dong, Seochon and Samcheong-dong",
    "JG": "Euljiro and Myeongdong",
    "MP": "Hongdae, Yeonnam-dong and Mangwon-dong",
    "SC": "Banpo, Seorae Village and the area around the Express Bus Terminal",
    "SD": "Seongsu-dong",
    "SP": "Jamsil and Songridan-gil",
    "YS": "Itaewon and Hannam-dong",
}
NUMBER_WORDS = {7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def district_count():
    return NUMBER_WORDS.get(len(DISTRICTS), str(len(DISTRICTS)))
REGISTERS = {"072404": "restaurant", "072405": "cafe"}


def services():
    return [(f"LOCALDATA_{reg}_{d}", d, reg) for d in DISTRICTS for reg in REGISTERS]


# The register's own type (업태구분명) in English, and the filter group it
# belongs to. "기타" is the register's "other" and says nothing, so it reads as
# the plain kind of place. An unknown type keeps its Korean and the group of
# its register, and the harvester prints it so the table can grow.
TYPES = {
    "한식": ("Korean", "restaurant"),
    "경양식": ("Western", "restaurant"),
    "기타": ("Restaurant", "restaurant"),
    "일식": ("Japanese", "restaurant"),
    "중국식": ("Chinese", "restaurant"),
    "외국음식전문점(인도,태국등)": ("International", "restaurant"),
    "분식": ("Snack food (bunsik)", "restaurant"),
    "김밥(도시락)": ("Gimbap and lunchboxes", "restaurant"),
    "냉면집": ("Cold noodles (naengmyeon)", "restaurant"),
    "뷔페식": ("Buffet", "restaurant"),
    "식육(숯불구이)": ("Korean barbecue", "restaurant"),
    "탕류(보신용)": ("Soups and stews", "restaurant"),
    "패밀리레스트랑": ("Family restaurant", "restaurant"),
    "패스트푸드": ("Fast food", "restaurant"),
    "통닭(치킨)": ("Fried chicken", "restaurant"),
    "복어취급": ("Pufferfish", "restaurant"),
    "횟집": ("Raw fish (hoe)", "restaurant"),
    "호프/통닭": ("Beer and chicken", "bar"),
    "정종/대포집/소주방": ("Soju bar", "bar"),
    "감성주점": ("Bar", "bar"),
    "라이브카페": ("Live music bar", "bar"),
    "단란주점": ("Karaoke bar", "bar"),
    "까페": ("Café", "cafe"),
    "커피숍": ("Coffee shop", "cafe"),
    "기타 휴게음식점": ("Café or snack bar", "cafe"),
    "다방": ("Tearoom (dabang)", "cafe"),
    "전통찻집": ("Traditional tea house", "cafe"),
    "떡카페": ("Rice-cake café", "cafe"),
    "키즈카페": ("Kids’ café", "cafe"),
    "과자점": ("Bakery", "cafe"),
    "아이스크림": ("Ice cream", "cafe"),
    "일반조리판매": ("Takeaway", "cafe"),
    "관광호텔": ("Hotel café", "cafe"),
}
GROUPS = {"restaurant": "Restaurants", "bar": "Bars", "cafe": "Cafés and bakeries"}

# Not a new place to go: shops, mobile kitchens, counters inside a station,
# a cinema, a motorway stop or an amusement park.
SKIP_TYPES = {"편의점", "푸드트럭", "출장조리", "이동조리", "철도역구내", "고속도로", "극장",
              "유원지", "백화점"}
# Department-store food halls and their pop-ups. Measured 10 October 2026 over
# the 30 days to 8 October: 61 of 572 names carried "(한시적)", temporary, and
# 86 sat at a department-store or food-hall address.
POPUP_NAME = re.compile(r"한시적|팝업|pop-?up", re.I)
FOOD_HALL_ADDRESS = re.compile(r"백화점|식품관|면세점|아울렛")
# The same, in a branch name: "사월에보리밥 청밀당 동대문현대아울렛점" sits in an
# outlet's food floor although its address names only the street (seen
# 10 October 2026, and AK플라자홍대점 in the first name sample).
SHARED_KITCHEN = re.compile(r"주방\s*\d+\s*호|공유주방")
DELIVERY_NAME = re.compile(r"배달전문|배달 전문|딜리버리|공유주방")
FOOD_HALL_NAME = re.compile(r"백화점|아울렛|면세점|AK플라자|식품관")
# A convenience store licensed as 기타 휴게음식점 (seating, or cooking on site)
# slips past SKIP_TYPES: 13 had, 21 August to 26 October 2026. Caught by the
# chain's name, his call of 29 October 2026. ⚠️ Anchored to the START of the
# name: unanchored, "CU" also caught 커비 Cubby, an Indian and Thai restaurant.
CONVENIENCE_NAME = re.compile(
    r"^\s*(씨유|CU(?![A-Za-z])|지에스\s*25|GS\s*25|세븐\s*일레븐|7-?eleven|이마트\s*24|emart\s*24|미니스톱|ministop)",
    re.I)


def type_info(type_ko, register):
    if type_ko in TYPES:
        return TYPES[type_ko]
    return (type_ko or ("Restaurant" if register == "072404" else "Café"),
            "restaurant" if register == "072404" else "cafe")


def exclusion(row):
    """Why this licence is not listed, or None. Pure, for tests."""
    t = (row.get("UPTAENM") or "").strip()
    if t in SKIP_TYPES:
        return f"type {t}"
    if CONVENIENCE_NAME.search(row.get("BPLCNM") or ""):
        return "convenience store"
    if POPUP_NAME.search(row.get("BPLCNM") or ""):
        return "temporary or pop-up"
    addr = (row.get("RDNWHLADDR") or "") + " " + (row.get("SITEWHLADDR") or "")
    if FOOD_HALL_ADDRESS.search(addr) or FOOD_HALL_NAME.search(row.get("BPLCNM") or ""):
        return "department store or food hall"
    # A numbered kitchen in a shared building ("지하2층 주방 24호") is a
    # delivery kitchen with no seats: left out, his call of 11 October 2026.
    if SHARED_KITCHEN.search(addr) or DELIVERY_NAME.search(row.get("BPLCNM") or ""):
        return "delivery only"
    return None


def reexclude(e):
    """exclusion() for a stored licence, so a rule added later reaches places
    already on the list. Uses only fields the record keeps."""
    return exclusion({"UPTAENM": e.get("type_ko"), "BPLCNM": e.get("name"),
                      "RDNWHLADDR": e.get("road"), "SITEWHLADDR": e.get("lot")})


LATIN = re.compile(r"[A-Za-z]")


def english_name(name):
    """The licence's own English, when it has one: a Latin name in brackets
    ("사보서울(SAVO SEOUL)" -> "SAVO SEOUL") or a name already in Latin script.
    Never a translation: that is the weekly pass's job."""
    for inner in re.findall(r"[(（]([^)）]+)[)）]", name or ""):
        if LATIN.search(inner) and not re.search(r"[가-힣]", inner):
            return inner.strip()
    if LATIN.search(name or "") and not re.search(r"[가-힣]", name or ""):
        return name.strip()
    return None


def neighborhood(road, lot):
    """The 동 (or 가) a road address names in its closing brackets, else the
    one in the lot address. Korean, as the register gives it."""
    m = re.search(r"\(([^,()]*?(?:동|가)\d*)(?:,[^)]*)?\)\s*$", road or "")
    if m:
        return m.group(1).strip()
    m = re.search(r"[구]\s+(\S+?(?:동|가)\d*)(?:\s|$)", lot or "")
    return m.group(1) if m else None


def lookup_address(road):
    """A road address up to the first comma,
    without the bracketed 동. "서울특별시 마포구 성미산로 161-11, 1층 (연남동)"
    -> "서울특별시 마포구 성미산로 161-11"."""
    a = re.sub(r"\s*\([^)]*\)\s*$", "", road or "")
    return a.split(",")[0].strip()


CORPORATE = re.compile(r"^\s*(주식회사|\(주\)|㈜|유한회사|농업회사법인)\s*|\s*(주식회사|\(주\)|㈜)\s*$")


def display_name(name):
    """The name without the company-form words a licence often carries:
    "주식회사 안목서초" -> "안목서초", "유동부치아바타(주)" -> "유동부치아바타"."""
    return CORPORATE.sub("", name or "").strip() or (name or "")


# ── The register's own coordinates ───────────────────────────────────────────
# Each register row carries X and Y in EPSG:5174 (Korean 1985, Bessel 1841,
# Transverse Mercator, central meridian 127°0'10.405", origin 38°N, false
# easting 200,000, false northing 500,000). They replaced Kakao's address search
# on 30 October 2026, his call: Kakao's staff say Local API results may not be
# stored in any form, only called live. Checked that day against Kakao's own
# pins for 226 places: median 2.8 m apart, 215 within 100 m, 3 over 200 m.
# The datum shift is EPSG:5174's published TOWGS84 (position vector).
_BESSEL_A, _BESSEL_F = 6377397.155, 1 / 299.1528128
_LON0, _LAT0, _FE, _FN = 127.0028902777778, 38.0, 200000.0, 500000.0
_TOWGS84 = (-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)


def register_point(x, y):
    """(lat, lon) in WGS84 from a register row's X and Y, or None when either
    is blank or not a number."""
    try:
        x, y = float(str(x).strip()), float(str(y).strip())
    except ValueError:
        return None
    if not x or not y:
        return None
    a, f = _BESSEL_A, _BESSEL_F
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)

    def meridian(phi):
        return a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
                    - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * phi)
                    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * phi)
                    - (35 * e2 ** 3 / 3072) * math.sin(6 * phi))

    m = meridian(math.radians(_LAT0)) + (y - _FN)
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
          + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1, t1 = ep2 * math.cos(p1) ** 2, math.tan(p1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = (x - _FE) / n1
    lat = p1 - (n1 * math.tan(p1) / r1) * (
        d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = math.radians(_LON0) + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                                 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2)
                                 * d ** 5 / 120) / math.cos(p1)
    # Bessel geodetic -> ECEF -> Helmert -> WGS84 geodetic
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    X = n * math.cos(lat) * math.cos(lon)
    Y = n * math.cos(lat) * math.sin(lon)
    Z = n * (1 - e2) * math.sin(lat)
    tx, ty, tz, rx, ry, rz, s = _TOWGS84
    rx, ry, rz = (math.radians(v / 3600) for v in (rx, ry, rz))
    s = 1 + s * 1e-6
    X, Y, Z = (tx + s * (X - rz * Y + ry * Z), ty + s * (rz * X + Y - rx * Z),
               tz + s * (-ry * X + rx * Y + Z))
    A, F = 6378137.0, 1 / 298.257223563
    E2 = F * (2 - F)
    p = math.hypot(X, Y)
    phi = math.atan2(Z, p * (1 - E2))
    for _ in range(6):
        phi = math.atan2(Z + E2 * A / math.sqrt(1 - E2 * math.sin(phi) ** 2) * math.sin(phi), p)
    return round(math.degrees(phi), 7), round(math.degrees(math.atan2(Y, X)), 7)
