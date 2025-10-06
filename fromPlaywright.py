from playwright.sync_api import sync_playwright

# 대상 URL
URL = "https://www.kcisa.kr/kr/contents/open_openData/view.do"
# 저장할 파일 경로
SCREENSHOT_PATH = "culture_full_page.png"
DOM_PATH = "kcisa_full_dom.html"
COORDINATES_PATH = "culture_link_coordinates.txt"

def scrape_kyobo_scholar():
    """
    Playwright를 사용하여 사이트에 접속, 스크린샷, DOM 추출 및 링크 좌표를 추출합니다.
    """
    with sync_playwright() as p:
        # 1. 브라우저 실행 (Headless 모드로 실행, 디버깅을 위해 False로 설정할 수도 있음)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 2. 사이트 접속 및 로딩
        print(f"1. 사이트 접속 및 로딩: {URL} 에 접속 중...")
        # 'load' 상태가 될 때까지 기다립니다. (모든 리소스 로딩 완료 대기)
        page.goto(URL, wait_until="load")
        print("   -> 접속 완료.")
        
        # 추가 대기: 동적 메뉴가 완전히 로드되도록 시간을 줍니다. (필요에 따라)
        # page.wait_for_timeout(3000) 
        
        # 3. Full-Page 스크린샷 캡처
        print(f"2. Full-Page 스크린샷 캡처: {SCREENSHOT_PATH} 저장 중...")
        # fullPage=True 옵션으로 전체 스크롤 가능한 페이지를 캡처
        page.screenshot(path=SCREENSHOT_PATH, full_page=True)
        print("   -> 스크린샷 저장 완료.")

        # 4. DOM 구조 추출 및 매핑
        print(f"3. DOM 구조 추출 및 매핑:")
        
        # 4.1. 전체 DOM 구조(HTML) 추출
        full_html = page.content()
        with open(DOM_PATH, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"   -> 전체 DOM 구조를 {DOM_PATH}에 저장 완료.")

        # 4.2. 주요 요소(예: 모든 링크 <a> 태그)의 좌표 추출 및 매핑
        # Playwright의 evaluate 함수를 사용하여 브라우저 환경에서 직접 좌표를 얻습니다.
        # document.querySelectorAll("a")는 페이지의 모든 <a> 요소를 찾습니다.
        # .map()을 사용하여 각 요소의 텍스트와 getBoundingClientRect()를 통해 시각적 좌표를 추출합니다.
        link_data = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a'));
            return links.map(link => {
                const rect = link.getBoundingClientRect();
                return {
                    text: link.textContent.trim().replace(/\\s+/g, ' '),
                    href: link.href,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                };
            }).filter(data => data.text && data.width > 0 && data.height > 0); // 텍스트가 있고, 크기가 0이 아닌 유효한 링크만 필터링
        }""")

        with open(COORDINATES_PATH, "w", encoding="utf-8") as f:
            for item in link_data:
                # 텍스트와 좌표를 한 줄로 출력
                f.write(f"TEXT: {item['text']} | HREF: {item['href']} | BBOX: x={item['x']}, y={item['y']}, w={item['width']}, h={item['height']}\n")
        
        print(f"   -> 모든 링크 요소의 텍스트 및 좌표를 {COORDINATES_PATH}에 저장 완료.")

        browser.close()

if __name__ == "__main__":
    scrape_kyobo_scholar()