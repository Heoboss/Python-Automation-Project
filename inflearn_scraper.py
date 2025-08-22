# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ⭐️ 함수가 limit 파라미터를 받도록 수정 (기본값은 10)
def scrape_inflearn(keyword, limit=10):
    """
    인프런에서 키워드로 강의를 검색하고 제목, 강사명, 평점, 분류, 가격, 링크를 반환합니다.
    """
    # --- CSS 선택자들 ---
    CARD_SELECTOR = 'div.css-12pmwg9>div[data-course-item="true"]' 
    TITLE_SELECTOR = 'p.css-10bh5qj' 
    INSTRUCTOR_SELECTOR = 'p.css-1r49xhh'
    RATING_SELECTOR = 'p.css-bh9d0c'
    CATEGORY_SELECTOR = 'p.css-1m5hyg0'
    LINK_SELECTOR = 'a'
    PRICE_SELECTOR = 'p.css-uzjboo.mantine-cm9qo8'

    base_url = "https://www.inflearn.com"
    search_url = f"{base_url}/courses?s={keyword}"
    
    options = webdriver.ChromeOptions()
    options.add_argument("headless")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    # ⭐️ 브라우저 언어 설정을 한국어로 강제하여 한국어 콘텐츠를 무조건 받도록 수정
    options.add_argument("--lang=ko-KR")
    # ⭐️ 선호 언어 설정도 한국어로 명시하여 안정성 강화
    options.add_experimental_option('prefs', {'intl.accept_languages': 'ko,ko_KR'})
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    results = []
    seen_titles = set()
    
    print(f"Selenium으로 '{keyword}' 검색 페이지 로딩 시작: {search_url}")

    try:
        driver.get(search_url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, CARD_SELECTOR))
        )
        
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        course_cards = soup.select(CARD_SELECTOR)
        
        if not course_cards:
            print("강의 목록을 찾지 못했습니다.")
            return []

        for card_html in course_cards:
            card = BeautifulSoup(str(card_html), 'html.parser')
            
            a_tag = card.select_one(LINK_SELECTOR)
            if not a_tag:
                continue

            title_tag = a_tag.select_one(TITLE_SELECTOR)
            
            if title_tag and title_tag.text.strip():
                title = title_tag.text.strip()
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                instructor_tag = a_tag.select_one(INSTRUCTOR_SELECTOR)
                instructor = instructor_tag.text.strip() if instructor_tag else "정보 없음"
                
                rating_tag = a_tag.select_one(RATING_SELECTOR)
                rating = rating_tag.text.strip() if rating_tag else "평점 없음"

                category_tag = a_tag.select_one(CATEGORY_SELECTOR)
                category = category_tag.text.strip() if category_tag else "분류 없음"

                price_tag = a_tag.select_one(PRICE_SELECTOR)
                price = price_tag.text.strip() if price_tag else "가격 정보 없음"

                link = a_tag.get('href', '링크 없음')
                
                results.append({
                    "title": title, 
                    "instructor": instructor,
                    "rating": rating,
                    "category": category,
                    "price": price,
                    "link": link
                })

            # ⭐️ 10 대신 limit 변수를 사용하도록 수정
            if len(results) == limit:
                break
        
        print(f"총 {len(results)}개의 유효한 강의 정보를 추출했습니다.")
        return results

    except TimeoutException:
        print(f"\n❌ 페이지에서 '{CARD_SELECTOR}'에 해당하는 강의 카드를 전혀 찾을 수 없습니다.")
        return []
    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
        return []
    finally:
        driver.quit()

# --- 테스트를 위한 코드 예시 ---
if __name__ == '__main__':
    # 5개만 가져오도록 테스트
    lectures = scrape_inflearn("파이썬", 5)
    if lectures:
        print(f"\n--- 검색 결과 (유효한 강의 상위 {len(lectures)}개) ---")
        for i, data in enumerate(lectures, 1):
            print(f"\n[{i}번째 강의]")
            print(f"  - 제목: {data['title']}")
            print(f"  - 강사: {data['instructor']}")
            print(f"  - 평점: {data['rating']}")
            print(f"  - 분류: {data['category']}")
            print(f"  - 가격: {data['price']}")
            print(f"  - 링크: {data['link']}")
