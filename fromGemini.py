import os
import json
from google import genai
from google.genai.errors import APIError
from bs4 import BeautifulSoup
import time # API 할당량 초과 시 재시도 간격을 위해 사용

# --- 설정 (Setting) ---g
HTML_FILE_PATH = "kcisa_full_dom.html"
JSON_OUTPUT_PATH = "gemini_extracted_kcisa_menu.json"

# API Key 설정: 발급받은 키를 환경 변수 'GEMINI_API_KEY'에 설정해야 합니다.
# 실제 사용 시 유효한 API 키로 변경하거나 환경 변수에 설정해야 합니다.
GEMINI_API_KEY = "A"

# --- JSON 스키마 정의 (최대 6 Depth까지 명시적 정의) ---

# 기본 메뉴 항목의 속성 및 필수 리스트 정의
BASE_ITEM_PROPERTIES = {
    "text": {"type": "string", "description": "메뉴의 텍스트"},
    "href": {"type": "string", "description": "메뉴의 URL"},
}
BASE_REQUIRED = ["text", "href"]

def create_item_schema(child_schema=None, depth_desc=""):
    """각 메뉴 뎁스에 대한 독립적인 JSON 스키마 정의를 생성합니다."""
    item = {
        "type": "object",
        # 속성 딕셔너리 복사
        "properties": BASE_ITEM_PROPERTIES.copy(), 
        # 필수 항목 리스트 복사 (매우 중요: 얕은 복사 방지)
        "required": list(BASE_REQUIRED) 
    }
    if child_schema:
        # 'children' 속성 추가
        item["properties"]["children"] = {
            "type": "array",
            "items": child_schema,
            "description": depth_desc
        }
        # 복사된 required 리스트에 'children' 추가
        item["required"].append("children")
    return item

# 6단계 (가장 깊은 레벨): children이 없습니다.
L6_ITEM = create_item_schema()

# 5단계: 6단계 children을 가집니다.
L5_ITEM = create_item_schema(child_schema=L6_ITEM, depth_desc="6뎁스 메뉴 목록")

# 4단계: 5단계 children을 가집니다.
L4_ITEM = create_item_schema(child_schema=L5_ITEM, depth_desc="5뎁스 메뉴 목록")

# 3단계: 4단계 children을 가집니다.
L3_ITEM = create_item_schema(child_schema=L4_ITEM, depth_desc="4뎁스 메뉴 목록")

# 2단계: 3단계 children을 가집니다.
L2_ITEM = create_item_schema(child_schema=L3_ITEM, depth_desc="3뎁스 메뉴 목록")

# 1단계: 2단계 children을 가집니다. (메인 'menu' 배열의 항목)
L1_ITEM = create_item_schema(child_schema=L2_ITEM, depth_desc="2뎁스 메뉴 목록")

# 최종 JSON 스키마
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "menu": {
            "type": "array",
            "description": "최상위 메뉴 목록 (1뎁스)",
            "items": L1_ITEM
        }
    },
    "required": ["menu"]
}


def extract_menu_with_gemini():
    """
    HTML 파일의 GNB 섹션을 추출하고, Gemini API를 사용하여
    재귀적인 메뉴 구조를 JSON으로 추출하는 함수입니다.
    """
    
    # 1. HTML 파일 로드 및 GNB 섹션 추출 (토큰 절약 핵심)
    try:
        with open(HTML_FILE_PATH, "r", encoding="utf-8") as f:
            full_html = f.read()
    except FileNotFoundError:
        print(f"오류: '{HTML_FILE_PATH}' 파일을 찾을 수 없습니다.")
        return

    soup = BeautifulSoup(full_html, 'html.parser')
    
    # <nav class="gnb__aligner"> 태그를 찾아 GNB 메뉴 섹션만 추출합니다.
    menu_section = soup.select_one('nav.gnb__aligner')
    if not menu_section:
        # 해당 셀렉터가 없으면 <header> 태그를 시도합니다.
        menu_section = soup.find('header')
        
    if menu_section:
        html_content = str(menu_section)
        print(f"1. HTML 파일 로드 완료. GNB 섹션만 ({len(html_content)} bytes) 추출 완료.")
    else:
        # 경고: GNB를 찾지 못하면 전체 HTML을 사용합니다.
        print("경고: GNB 섹션을 찾지 못했습니다. 전체 HTML을 사용합니다. 할당량 초과 가능성이 높습니다.")
        html_content = full_html
    
    # 2. Gemini 클라이언트 초기화
    if not GEMINI_API_KEY:
        print("오류: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다. 환경 변수를 확인하세요.")
        return
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 3. 프롬프트 정의 (최대 Depth 6을 LLM에게 강력하게 요구)
    system_instruction = (
        "당신은 웹사이트 HTML에서 GNB 메뉴 구조를 추출하는 전문 파서입니다. "
        "응답은 반드시 요청된 JSON 스키마를 엄격하게 따라야 하며, 다른 텍스트나 설명은 절대 포함하지 마세요."
        "**모든 메뉴 항목(1뎁스부터 5뎁스까지)은 'children' 배열을 가져야 하며, 최종 6뎁스 항목에는 'children'이 없습니다.** "
        "각 항목은 'text'와 'href'를 포함해야 합니다."
    )
    
    user_prompt = f"""
    아래 HTML 코드에서 웹사이트의 주 메뉴(GNB) 구조를 추출하고 JSON으로 만들어줘.
    요청된 JSON 스키마는 **최대 6단계 깊이**의 메뉴 구조를 명시적으로 지원합니다.
    실제 메뉴 깊이에 맞게 'children' 배열을 중첩시켜 구조를 표현해야 합니다.

    [HTML 내용]
    {html_content}
    """
    
    # 4. API 호출 및 오류 처리 루프
    max_retries = 3
    retry_delay = 30 # 초
    
    for attempt in range(max_retries):
        try:
            print(f"2. Gemini API 호출 시도 중... (시도 {attempt + 1}/{max_retries})")
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=JSON_SCHEMA
                )
            )

            # 5. 응답 처리 및 JSON 추출
            json_string = response.text
            menu_data = json.loads(json_string)

            # 6. 최종 파일 저장
            with open(JSON_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                json.dump(menu_data, f, ensure_ascii=False, indent=4)
            
            print(f"\n3. LLM 추출 성공. 메뉴 구조를 {JSON_OUTPUT_PATH}에 저장 완료.")
            return

        except APIError as e:
            if "RESOURCE_EXHAUSTED" in str(e) and attempt < max_retries - 1:
                print(f"\nAPI 오류 발생: 할당량 초과 (429). {retry_delay}초 후 재시도합니다.")
                time.sleep(retry_delay)
            elif "API key not valid" in str(e):
                print(f"\nAPI 오류 발생: API Key가 유효하지 않습니다 (400). 키 설정을 확인하세요.")
                return
            else:
                print(f"\nAPI 오류 발생: {e}")
                return
        except json.JSONDecodeError:
            # LLM이 스키마를 따르지 않고 다른 텍스트를 포함하거나 구조를 잘못 만든 경우
            print("\n오류: Gemini 응답이 유효한 JSON 형식이 아닙니다. LLM이 요청된 형식을 따르지 않았습니다.")
            # 오류 진단을 돕기 위해 응답의 첫 부분을 출력
            print(f"LLM 응답 원본:\n{response.text[:500]}...") 
            return
        except Exception as e:
            print(f"\n예기치 않은 오류 발생: {e}")
            return
            
    print("\n최대 재시도 횟수를 초과했습니다. API 할당량이 고갈되었을 수 있습니다. 잠시 후 다시 시도하세요.")

if __name__ == "__main__":
    extract_menu_with_gemini()
