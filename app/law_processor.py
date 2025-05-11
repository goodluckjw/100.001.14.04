import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
import re
import os
import unicodedata
from collections import defaultdict

OC = os.getenv("OC", "chetera")
BASE = "http://www.law.go.kr"

def get_law_list_from_api(query):
    exact_query = f'"{query}"'
    encoded_query = quote(exact_query)
    page = 1
    laws = []
    while True:
        url = f"{BASE}/DRF/lawSearch.do?OC={OC}&target=law&type=XML&display=100&page={page}&search=2&knd=A0002&query={encoded_query}"
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        if res.status_code != 200:
            break
        root = ET.fromstring(res.content)
        for law in root.findall("law"):
            laws.append({
                "법령명": law.findtext("법령명한글", "").strip(),
                "MST": law.findtext("법령일련번호", "")
            })
        if len(root.findall("law")) < 100:
            break
        page += 1
    return laws

def get_law_text_by_mst(mst):
    url = f"{BASE}/DRF/lawService.do?OC={OC}&target=law&MST={mst}&type=XML"
    try:
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        return res.content if res.status_code == 200 else None
    except:
        return None

def clean(text):
    return re.sub(r"\s+", "", text or "")

def normalize_number(text):
    try:
        return str(int(unicodedata.numeric(text)))
    except:
        return text

def make_article_number(조문번호, 조문가지번호):
    if 조문가지번호 and 조문가지번호 != "0":
        return f"제{조문번호}조의{조문가지번호}"
    else:
        return f"제{조문번호}조"

def format_location(loc):
    padded = loc + (None,) * (5 - len(loc))
    조, 항, 호, 목, _ = padded[:5]
    parts = []
    if 조: parts.append(f"{조}")
    if 항: parts.append(f"{항}항")
    if 호: parts.append(f"{호}호")
    if 목: parts.append(f"{목}목")
    return "".join(parts)

def get_jongseong_type(word):
    last_char = word[-1]
    code = ord(last_char)
    if not (0xAC00 <= code <= 0xD7A3):
        return (False, False)
    jong = (code - 0xAC00) % 28
    return jong != 0, jong == 8

def extract_chunk_and_josa(token, searchword):
    suffix_list = ["으로", "이나", "과", "와", "을", "를", "이", "가", "나", "로", "은", "는"]
    pattern = re.compile(rf'({re.escape(searchword)})(?:{"|".join(suffix_list)})?$')
    m = pattern.search(token)
    if m:
        return m.group(1), m.group(2) if m.lastindex == 2 else None
    return token, None


def group_locations(loc_list):
    grouped = defaultdict(list)
    for loc in loc_list:
        m = re.match(r'(제\d+조)(.*)', loc)
        if m:
            grouped[m.group(1)].append(m.group(2))
        else:
            grouped[loc].append('')
    result = []
    for 조, 항목들 in grouped.items():
        항목들 = [a for a in 항목들 if a]
        if 항목들:
            result.append(조 + 'ㆍ'.join(항목들))
        else:
            result.append(조)
    return ' 및 '.join(result) if len(result) > 1 else result[0]

def apply_josa_rule(a, b, josa=None):
    b_has_batchim, b_has_rieul = get_jongseong_type(b)
    a_has_batchim, _ = get_jongseong_type(a)

    if not josa:
        if not a_has_batchim:
            if not b_has_batchim or b_has_rieul:
                return f'"{a}"를 "{b}"로 한다.'
            else:
                return f'"{a}"를 "{b}"으로 한다.'
        else:
            if not b_has_batchim or b_has_rieul:
                return f'"{a}"을 "{b}"로 한다.'
            else:
                return f'"{a}"을 "{b}"으로 한다.'

    if josa == "을":
        return f'"{a}"을 "{b}"{"로" if b_has_rieul else "으로" if b_has_batchim else "를"} 한다.'
    if josa == "를":
        return f'"{a}"를 "{b}"{"을" if b_has_batchim else "로"} 한다.'
    if josa == "과":
        return f'"{a}"과 "{b}"{"과" if b_has_batchim else "와"} 한다.'
    if josa == "와":
        return f'"{a}"와 "{b}"{"과" if b_has_batchim else "와"} 한다.'
    if josa == "이":
        return f'"{a}"이 "{b}"{"로" if b_has_rieul else "으로" if b_has_batchim else "가"} 한다.'
    if josa == "가":
        return f'"{a}"가 "{b}"{"이" if b_has_batchim else ""} 한다.'
    if josa == "이나":
        return f'"{a}"이나 "{b}"{"이나" if b_has_batchim else "나"} 한다.'
    if josa == "나":
        return f'"{a}"나 "{b}"{"이나" if b_has_batchim else ""} 한다.'
    if josa == "으로":
        return f'"{a}"으로 "{b}"{"로" if b_has_rieul or not b_has_batchim else "으로"} 한다.'
    if josa == "로":
        return f'"{a}"로 "{b}"{"으로" if b_has_batchim and not b_has_rieul else ""} 한다.'
    if josa == "는":
        return f'"{a}"는 "{b}"{"은" if b_has_batchim else ""} 한다.'
    if josa == "은":
        return f'"{a}"은 "{b}"{"은" if b_has_batchim else "는"} 한다.'
    return f'"{a}"를 "{b}"로 한다.'

def run_amendment_logic(find_word, replace_word):
    amendment_results = []
    for idx, law in enumerate(get_law_list_from_api(find_word)):
        law_name = law["법령명"]
        mst = law["MST"]
        xml_data = get_law_text_by_mst(mst)
        if not xml_data:
            continue

        tree = ET.fromstring(xml_data)
        articles = tree.findall(".//조문단위")
        chunk_map = defaultdict(list)

        for article in articles:
            조번호 = article.findtext("조문번호", "").strip()
            조가지번호 = article.findtext("조가지번호", "").strip()
            조문식별자 = make_article_number(조번호, 조가지번호)
            조문내용 = article.findtext("조문내용", "") or ""

            tokens = re.findall(r'[가-힣A-Za-z0-9]+', 조문내용)
            for token in tokens:
                if find_word in token:
                    chunk, josa = extract_chunk_and_josa(token, find_word)
                    바꿀덩어리 = chunk.replace(find_word, replace_word)
                    loc_str = f"{조문식별자}"
                    chunk_map[(chunk, 바꿀덩어리, josa)].append(loc_str)

        if not chunk_map:
            continue

        문장들 = []
        for (chunk, 바꿀덩어리, josa), locs in chunk_map.items():
            각각 = "각각 " if len(locs) > 1 else ""
            locs_str = group_locations(locs)
            문장들.append(f'{locs_str} 중 {apply_josa_rule(chunk, 바꿀덩어리, josa)}')

        prefix = chr(9312 + idx) if idx < 20 else str(idx + 1)
        amendment_results.append(f"{prefix} {law_name} 일부를 다음과 같이 개정한다.<br>" + "<br>".join(문장들))

    return amendment_results if amendment_results else ["⚠️ 개정 대상 조문이 없습니다."]


# 아래에 run_search_logic 삽입

# 개선된 run_search_logic 함수
def run_search_logic(query, unit="법률"):
    result_dict = {}
    keyword_clean = clean(query)

    for law in get_law_list_from_api(query):
        mst = law["MST"]
        xml_data = get_law_text_by_mst(mst)
        if not xml_data:
            continue

        tree = ET.fromstring(xml_data)
        articles = tree.findall(".//조문단위")
        law_results = []

        for article in articles:
            조번호 = article.findtext("조문번호", "").strip()
            조가지번호 = article.findtext("조문가지번호", "").strip()
            조문식별자 = make_article_number(조번호, 조가지번호)
            조문내용 = article.findtext("조문내용", "") or ""
            항들 = article.findall("항")
            출력덩어리 = []
            조출력 = keyword_clean in clean(조문내용)
            첫_항출력됨 = False

            if 조출력:
                출력덩어리.append(highlight(조문내용, query))

            for 항 in 항들:
                항번호 = normalize_number(항.findtext("항번호", "").strip())
                항내용 = 항.findtext("항내용", "") or ""
                항출력 = keyword_clean in clean(항내용)
                항덩어리 = []
                하위검색됨 = False

                for 호 in 항.findall("호"):
                    호내용 = 호.findtext("호내용", "") or ""
                    호출력 = keyword_clean in clean(호내용)
                    if 호출력:
                        하위검색됨 = True
                        항덩어리.append("&nbsp;&nbsp;" + highlight(호내용, query))

                    for 목 in 호.findall("목"):
                        for m in 목.findall("목내용"):
                            if m.text and keyword_clean in clean(m.text):
                                줄들 = [line.strip() for line in m.text.splitlines() if line.strip()]
                                줄들 = [highlight(line, query) for line in 줄들]
                                if 줄들:
                                    하위검색됨 = True
                                    항덩어리.append(
                                        "<div style='margin:0;padding:0'>" +
                                        "<br>".join("&nbsp;&nbsp;&nbsp;&nbsp;" + line for line in 줄들) +
                                        "</div>"
                                    )

                if 항출력 or 하위검색됨:
                    if not 조출력 and not 첫_항출력됨:
                        출력덩어리.append(f"{highlight(조문내용, query)} {highlight(항내용, query)}")
                        첫_항출력됨 = True
                    elif not 첫_항출력됨:
                        출력덩어리.append(highlight(항내용, query))
                        첫_항출력됨 = True
                    else:
                        출력덩어리.append(highlight(항내용, query))
                    출력덩어리.extend(항덩어리)

            if 출력덩어리:
                law_results.append("<br>".join(출력덩어리))

        if law_results:
            result_dict[law["법령명"]] = law_results

    return result_dict

