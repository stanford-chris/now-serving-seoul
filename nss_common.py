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
    "YS": ("Yongsan", "용산구"),
}
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
    if FOOD_HALL_ADDRESS.search(addr):
        return "department store or food hall"
    return None


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
