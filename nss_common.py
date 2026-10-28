"""Now Serving Seoul: what the harvester and the site builder share.

The source is Seoul's food-licence register (지방행정 인허가 데이터, published
per district on data.seoul.go.kr under 공공누리 Type 1: credit the source,
commercial use and changes allowed). Two registers per district:
일반음식점 (072404, restaurants and most bars) and 휴게음식점 (072405, cafés,
bakeries, snack counters).
"""
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
GEOCODE_CACHE = DATA / "geocode.json"

API = "http://openapi.seoul.go.kr:8088/{key}/json/{svc}/{a}/{b}/"
KEYCHAIN = ("seoul-open-data", "openapi.seoul.go.kr")    # service, account
KAKAO_KEYCHAIN = ("kakao-rest-api-key", "kakao-local")   # service, account
KAKAO_ADDRESS = "https://dapi.kakao.com/v2/local/search/address.json"

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
    "호프/통닭": ("Beer and chicken (hof)", "bar"),
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
    """The part of a road address Kakao can find: up to the first comma,
    without the bracketed 동. "서울특별시 마포구 성미산로 161-11, 1층 (연남동)"
    -> "서울특별시 마포구 성미산로 161-11"."""
    a = re.sub(r"\s*\([^)]*\)\s*$", "", road or "")
    return a.split(",")[0].strip()


CORPORATE = re.compile(r"^\s*(주식회사|\(주\)|㈜|유한회사|농업회사법인)\s*|\s*(주식회사|\(주\)|㈜)\s*$")


def display_name(name):
    """The name without the company-form words a licence often carries:
    "주식회사 안목서초" -> "안목서초", "유동부치아바타(주)" -> "유동부치아바타"."""
    return CORPORATE.sub("", name or "").strip() or (name or "")
