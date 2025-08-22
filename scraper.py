# -*- coding: utf-8 -*-
import concurrent.futures
from selenium import webdriver as wb
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time, urllib.parse

def get_section_text(driver, section_title):
    try:
        xpath = f"//h3[text()='{section_title}']/following-sibling::*[1]"
        # 상세 페이지 로딩이 느릴 수 있으므로 짧은 대기 추가
        element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return element.text
    except TimeoutException:
        return "정보 없음"

def get_summary_text(driver, summary_title):
    try:
        xpath = f"//dt[contains(text(), '{summary_title}')]/following-sibling::dd[1]"
        element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return element.text
    except TimeoutException:
        return "정보 없음"


# --- 잡플래닛 크롤링 함수 (URL 직접 접속 방식으로 수정) ---
def scrape_jobplanet(keyword, count):
    scraped_data = []
    options = wb.ChromeOptions()
    print("헤드리스 모드로 실행합니다.")
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    driver = wb.Chrome(options=options)
    
    try:
        # [수정] 검색 URL을 직접 생성하여 접속
        encoded_keyword = urllib.parse.quote(keyword)
        search_url = f"https://www.jobplanet.co.kr/search/job?query={encoded_keyword}"
        driver.get(search_url)
        print(f"잡플래닛 접속: {search_url}")

        if count > 7:
            driver.maximize_window()

        wait = WebDriverWait(driver, 10)
        
        # 팝업창 처리
        try:
            popup_iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//iframe[@title='Modal Message']"))
            )
            driver.switch_to.frame(popup_iframe)
            close_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[text()='닫기']"))
            )
            close_button.click()
            driver.switch_to.default_content()
            print("팝업창을 닫았습니다.")
            time.sleep(1)
        except TimeoutException:
            print("팝업창이 나타나지 않았습니다. 계속 진행합니다.")
        
        # [삭제] '채용' 탭 클릭 로직이 더 이상 필요 없음

        # ... (이하 스크롤 및 데이터 수집 로직은 기존과 동일)
        title_class_name = "line-clamp-2 break-all text-h7 text-gray-800 group-[.small]:text-h8"
        job_post_xpath = f"//a[.//h4[@class='{title_class_name}']]"
        wait.until(EC.presence_of_element_located((By.XPATH, job_post_xpath)))

        while True:
            job_post_elements = driver.find_elements(By.XPATH, job_post_xpath)
            if len(job_post_elements) >= count:
                print(f"요청한 {count}개 이상의 공고를 로드하여 스크롤을 중단합니다.")
                break
            
            before_scroll_count = len(job_post_elements)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

            after_scroll_count = len(driver.find_elements(By.XPATH, job_post_xpath))
            if after_scroll_count == before_scroll_count:
                print("페이지의 끝에 도달하여 더 이상 스크롤할 수 없습니다.")
                break

        final_job_elements = driver.find_elements(By.XPATH, job_post_xpath)
        links_to_visit = [post.get_attribute('href') for post in final_job_elements[:count]]
        
        for i, link in enumerate(links_to_visit):
            print(f"Scraping JobPlanet... {i+1}/{len(links_to_visit)}")
            driver.execute_script(f"window.open('{link}');")
            driver.switch_to.window(driver.window_handles[1])
            
            job_details = {"link": link}
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "recruitment-summary")))
                job_details["title"] = driver.find_element(By.CSS_SELECTOR, "h1.ttl").text
                job_details["company"] = driver.find_element(By.CSS_SELECTOR, "span.company_name a").text
                job_details["deadline"] = get_summary_text(driver, "마감일")
                job_details["skills"] = get_summary_text(driver, "스킬")
                job_details["location"] = get_section_text(driver, "회사위치")
                job_details["main_tasks"] = get_section_text(driver, "주요 업무")
                job_details["qualifications"] = get_section_text(driver, "자격 요건")
                job_details["preferred"] = get_section_text(driver, "우대사항")
                job_details["hiring_process"] = get_section_text(driver, "채용 절차")
                scraped_data.append(job_details)
            except Exception as e:
                print(f"Error scraping details for {link}: {e}")
            
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(1)

    except Exception as e:
        print(f"An unexpected error occurred in scrape_jobplanet: {e}")
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
        return scraped_data

# --- 잡코리아 크롤링 함수 (새롭게 구현) ---
def scrape_jobkorea_simple(keyword, count):
    print(f"잡코리아에서 '{keyword}'에 대한 공고 {count}개를 검색합니다.")
    scraped_data = []

    options = wb.ChromeOptions()
    print("헤드리스 모드로 실행합니다.")
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    driver = wb.Chrome(options=options)
    
    try:
        driver.get("https://www.jobkorea.co.kr/")
        driver.maximize_window()
        wait = WebDriverWait(driver, 10)

        search_input = wait.until(EC.presence_of_element_located((By.ID, "stext")))
        search_input.send_keys(keyword)
        search_input.send_keys(Keys.ENTER)

        job_container_class = "h7nnv10"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"div[class*='{job_container_class}']")))
        
        while True:
            job_postings = driver.find_elements(By.CSS_SELECTOR, f"div[class*='{job_container_class}']")
            if len(job_postings) >= count:
                print(f"요청한 {count}개 이상의 공고를 로드하여 스크롤을 중단합니다.")
                break
            
            before_scroll_count = len(job_postings)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

            after_scroll_count = len(driver.find_elements(By.CSS_SELECTOR, f"div[class*='{job_container_class}']"))
            if after_scroll_count == before_scroll_count:
                print("페이지의 끝에 도달하여 더 이상 스크롤할 수 없습니다.")
                break

        job_postings = driver.find_elements(By.CSS_SELECTOR, f"div[class*='{job_container_class}']")

        company_class = "Typography_variant_size16__344nw26 Typography_weight_regular__344nw2d Typography_color_gray900__344nw2k"
        title_class = "Typography_variant_size18__344nw25 Typography_weight_medium__344nw2c Typography_color_gray900__344nw2k"

        for post in job_postings[:count]:
            try:
                company = post.find_element(By.CSS_SELECTOR, f"span[class='{company_class}']").text
                title_element = post.find_element(By.CSS_SELECTOR, f"span[class='{title_class}']")
                title = title_element.text
                link = title_element.find_element(By.XPATH, "./ancestor::a").get_attribute('href')
                
                scraped_data.append({"company": company, "title": title, "link": link})
            except (NoSuchElementException, IndexError) as e:
                print(f"공고 처리 중 오류 발생 (건너뜁니다): {e}")
                continue

    except Exception as e:
        print(f"An unexpected error occurred in scrape_jobkorea: {e}")
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
        return scraped_data
    
# 인크루트 크롤링 함수
def scrape_incruit(keyword: str, count: int):
    """
    주어진 키워드로 인크루트 채용 정보를 스크래핑하는 함수.
    """
    print(f"인크루트에서 '{keyword}' 키워드로 {count}개 검색을 시작합니다.")
    scraped_data = []
    
    options = wb.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 1.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    #service = Service(ChromeDriverManager().install())
    #driver = wb.Chrome(service=service, options=options)
    driver = wb.Chrome(options=options)
    
    try:
        encoded_keyword = urllib.parse.quote(keyword)
        url_incruit = f"https://search.incruit.com/list/search.asp?col=job&kw={encoded_keyword}&memty=2000"
        
        driver.get(url_incruit)
        driver.maximize_window()
        
        wait = WebDriverWait(driver, 10)
        job_list_container_xpath = "//ul[contains(@class, 'c_row')]"
        wait.until(EC.presence_of_element_located((By.XPATH, job_list_container_xpath)))
        
        job_postings = driver.find_elements(By.XPATH, job_list_container_xpath)
        
        print(f"인크루트에서 총 {len(job_postings)}개의 공고를 찾았습니다. {count}개를 수집합니다.")

        for post in job_postings[:count]:
            try:
                company_name = post.find_element(By.CSS_SELECTOR, "a.cpname").text
                
                title_element = post.find_element(By.CSS_SELECTOR, "div.cell_mid > div.cl_top > a")
                job_title = title_element.text
                job_link = title_element.get_attribute('href')
                
                details_spans = post.find_elements(By.CSS_SELECTOR, "div.cl_md > span")
                
                location = details_spans[0].text if len(details_spans) > 0 else "정보 없음"
                experience = details_spans[1].text if len(details_spans) > 1 else "정보 없음"
                education = details_spans[2].text if len(details_spans) > 2 else "정보 없음"

                scraped_data.append({
                    "company": company_name,
                    "title": job_title,
                    "link": job_link,
                    "location": location,
                    "experience": experience,
                    "education": education
                })
            except NoSuchElementException:
                print("인크루트 공고 처리 중 일부 요소를 찾을 수 없어 건너뜁니다.")
                continue

    except Exception as e:
        print(f"인크루트 크롤링 중 오류가 발생했습니다: {e}")
        
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
        return scraped_data

