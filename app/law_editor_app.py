import streamlit as st
import os
import importlib.util

st.set_page_config(layout="wide")

st.markdown("<h1 style='font-size:20px;'>📘 부칙개정 도우미 (100.001.14.04)</h1>", unsafe_allow_html=True)

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
processor_path = os.path.join(base_dir, "law_processor.py")
spec = importlib.util.spec_from_file_location("law_processor", processor_path)
law_processor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(law_processor)

run_amendment_logic = law_processor.run_amendment_logic
# run_search_logic = lambda q, u: {}  # placeholder (기본형에서 미사용)
run_search_logic = law_processor.run_search_logic 

with st.expander("ℹ️ 사용법 안내"):
    st.markdown(      
             "- 이 앱은 다음 두 가지 기능을 제공합니다:\n"
        "  1. **검색 기능**: 검색어가 포함된 법률 조항을 반환합니다.\n"
        "     - 문장 검색 시 큰 따옴표는 필요하지 않습니다.\n"
        "     - 단일검색어 기반입니다. \n"
        "     - 다중검색어 또는 논리연산자(AND, OR, NOT 등)는 지원하지 않습니다. 언젠가 기능이 추가될 수도 있어요. 언젠가는.\n" 
        "  2. **개정문 생성**: 특정 단어를 다른 단어로 대체하는 부칙 개정문을 자동 생성합니다.\n"
        "     - 21번째 항목부터는 원문자가 아닌 일반숫자로 항목 번호가 표기됩니다. 오류가 아닙니다. 개선예정.\n" 
        "- 이 앱은 업무망에서는 작동하지 않습니다. 인터넷망에서 사용해주세요. \n"
        "- 속도가 느립니다. 네트워크 속도나 시스템 성능 탓이 아닙니다. 원래 느린 앱이예요. \n"
        "- 오류가 있을 수 있습니다. 오류를 발견하시는 분은 사법법제과 김재우(jwkim@assembly.go.kr)로 알려주시면 감사하겠습니다. (캡쳐파일도 같이 주시면 좋아요)"
    )
  
st.header("🔍 검색 기능")
search_query = st.text_input("검색어 입력", key="search_query")
do_search = st.button("검색 시작")
if do_search and search_query:
    with st.spinner("🔍 검색 중..."):
        result = law_processor.run_search_logic(search_query, unit="법률")
        st.success(f"{len(result)}개의 법률을 찾았습니다")
        for law_name, sections in result.items():
            with st.expander(f"📄 {law_name}"):
                for html in sections:
                    st.markdown(html, unsafe_allow_html=True)

st.header("✏️ 타법개정문 생성")
find_word = st.text_input("찾을 단어")
replace_word = st.text_input("바꿀 단어")
do_amend = st.button("개정문 생성")

if do_amend and find_word and replace_word:
    with st.spinner("🛠 개정문 생성 중..."):
        result = run_amendment_logic(find_word, replace_word)
        st.success("개정문 생성 완료")
        for amend in result:
            st.markdown(amend, unsafe_allow_html=True)
