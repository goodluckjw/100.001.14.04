
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

def 조사_을를(word):
    if not word:
        return "을"
    code = ord(word[-1]) - 0xAC00
    jong = code % 28
    return "를" if jong == 0 else "을"

def 조사_으로로(word):
    if not word:
        return "으로"
    code = ord(word[-1]) - 0xAC00
    jong = code % 28
    return "로" if jong == 0 or jong == 8 else "으로"

def highlight(text, keyword):
    escaped = re.escape(keyword)
    return re.sub(f"({escaped})", r"<span style='color:red'>\1</span>", text or "")

def remove_unicode_number_prefix(text):
    return re.sub(r"^[①-⑳]+", "", text)

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

def extract_chunks(text, keyword):
    match = re.search(rf"(\w*{re.escape(keyword)}\w*)", text)
    return match.group(1) if match else None

def format_location(loc):
    조, 항, 호, 목 = loc  # ✅ 네 개만 받도록 수정
    parts = [조]
    if 항:
        parts.append(f"제{항}항")
    if 호:
        parts.append(f"제{호}호")
    if 목:
        parts.append(f"{목}목")
    return "".join(parts)


# 아래에 run_search_logic과 run_amendment_logic 삽입

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




# 아래에 개정문 로직만 수정된 run_amendment_logic 삽입
# ✅ 조사 규칙 적용된 버전(coded by Claude)

from collections import defaultdict
import re

def get_jongseong_type(word):
    """받침 유무 및 ㄹ 여부 반환"""
    last_char = word[-1]
    code = ord(last_char)
    if not (0xAC00 <= code <= 0xD7A3):
        return False, False
    jong = (code - 0xAC00) % 28
    return jong != 0, jong == 8

def extract_josa(word):
    """단어에서 조사 추출"""
    josa_list = ["으로", "이나", "과", "와", "을", "를", "이", "가", "나", "로", "은", "는"]
    for josa in josa_list:
        if word.endswith(josa):
            return josa
    return ""

def apply_josa_rule(find_word, replace_word):
    """조사규칙에 따라 치환 표현 반환"""
    josa = extract_josa(find_word)
    root = find_word[:-len(josa)] if josa else find_word
    b_has_jong, b_has_rieul = get_jongseong_type(replace_word)
    a_has_jong, _ = get_jongseong_type(root)

    if not josa:
        if not a_has_jong:
            return f'"{find_word}"를 "{replace_word}"{"로" if not b_has_jong or b_has_rieul else "으로"} 한다.'
        else:
            return f'"{find_word}"을 "{replace_word}"{"로" if not b_has_jong or b_has_rieul else "으로"} 한다.'

    rule_map = {
        "을": lambda: f'"{root}"을 "{replace_word}"{"로" if b_has_rieul else "으로" if b_has_jong else "를"} 한다.',
        "를": lambda: f'"{root}"를 "{replace_word}"{"을" if b_has_jong else ""}로 한다.',
        "과": lambda: f'"{root}"과 "{replace_word}"{"로" if b_has_rieul else "으로" if b_has_jong else "와"} 한다.',
        "와": lambda: f'"{root}"와 "{replace_word}"{"과" if b_has_jong else ""}로 한다.',
        "이": lambda: f'"{root}"이 "{replace_word}"{"로" if b_has_rieul else "으로" if b_has_jong else "가"} 한다.',
        "가": lambda: f'"{root}"가 "{replace_word}"{"이" if b_has_jong else ""}로 한다.',
        "이나": lambda: f'"{root}"이나 "{replace_word}"{"로" if b_has_rieul else "으로" if b_has_jong else "나"} 한다.',
        "나": lambda: f'"{root}"나 "{replace_word}"{"이나" if b_has_jong else ""}로 한다.',
        "으로": lambda: f'"{root}"으로 "{replace_word}"{"로" if b_has_rieul or not b_has_jong else "으로"} 한다.',
        "로": lambda: f'"{root}"로 "{replace_word}"{"로" if not b_has_jong or b_has_rieul else "으로"} 한다.',
        "는": lambda: f'"{root}"는 "{replace_word}"{"은" if b_has_jong else ""}로 한다.',
        "은": lambda: f'"{root}"은 "{replace_word}"{"로" if b_has_rieul else "으로" if b_has_jong else "는"}로 한다.',
    }

    return rule_map.get(josa, lambda: f'"{find_word}"를 "{replace_word}"로 한다.')()

def format_location(loc):
    """조, 항, 호, 목 문자열 조립"""
    조, 항, 호, 목 = loc
    parts = [조]
    if 항:
        parts.append(f"제{항}항")
    if 호:
        parts.append(f"제{호}호")
    if 목:
        parts.append(f"{목}목")
    return "".join(parts)

def run_amendment_logic(find_word, replace_word):
    """개정문 생성 - 규칙 기반, 조사형 묶음 출력"""
    amendment_results = []
    for idx, law in enumerate(get_law_list_from_api(find_word)):
        law_name = law["법령명"]
        mst = law["MST"]
        xml_data = get_law_text_by_mst(mst)
        if not xml_data:
            continue

        tree = ET.fromstring(xml_data)
        articles = tree.findall(".//조문단위")

        # 위치별 조사형 그룹화
        grouped = defaultdict(list)

        for article in articles:
            조번호 = article.findtext("조문번호", "").strip()
            조가지번호 = article.findtext("조문가지번호", "").strip()
            조문식별자 = make_article_number(조번호, 조가지번호)
            조문내용 = article.findtext("조문내용", "") or ""
            if find_word in 조문내용:
                key = apply_josa_rule(find_word, replace_word)
                grouped[key].append((조문식별자, None, None, None))

            for 항 in article.findall("항"):
                항번호 = normalize_number(항.findtext("항번호", "").strip())
                항내용 = 항.findtext("항내용", "") or ""
                if find_word in 항내용:
                    key = apply_josa_rule(find_word, replace_word)
                    grouped[key].append((조문식별자, 항번호, None, None))

                for 호 in 항.findall("호"):
                    호번호 = 호.findtext("호번호", "").strip().replace(".", "")
                    호내용 = 호.findtext("호내용", "") or ""
                    if find_word in 호내용:
                        key = apply_josa_rule(find_word, replace_word)
                        grouped[key].append((조문식별자, 항번호, 호번호, None))

                    for 목 in 호.findall("목"):
                        목번호 = 목.findtext("목번호", "").strip().replace(".", "")
                        for m in 목.findall("목내용"):
                            if m.text and find_word in m.text:
                                key = apply_josa_rule(find_word, replace_word)
                                grouped[key].append((조문식별자, 항번호, 호번호, 목번호))

        # 문장 조립
        문장들 = []
        for key, locs in grouped.items():
            locs_sorted = sorted(set(locs))  # 중복 제거
            loc_str = ", ".join([format_location(l) for l in locs_sorted[:-1]]) + (" 및 " if len(locs_sorted) > 1 else "") + format_location(locs_sorted[-1])
            문장들.append(f'{loc_str} 중 {key}')

        if 문장들:
            prefix = chr(9312 + idx) if idx < 20 else str(idx + 1)
            amendment_results.append(f"{prefix} {law_name} 일부를 다음과 같이 개정한다.<br>" + "<br>".join(문장들))

    return amendment_results if amendment_results else ["⚠️ 개정 대상 조문이 없습니다."]
