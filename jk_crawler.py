# jk_crawler.py
# pip install selenium webdriver-manager

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Iterable
import time, tempfile, shutil, atexit, random, re, calendar
from urllib.parse import urlencode
from datetime import date, timedelta

from selenium import webdriver as wb
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

__all__ = [
    "Job",
    "crawl_latest_newbie",
    "crawl_latest_all",
    "search_jobs",
]

# ------------------ 데이터 모델 ------------------
@dataclass
class Job:
    title: str
    company: str
    url: str
    location: str = ""
    career: str = ""
    deadline: str = ""          # 원문(문자열) 저장
    deadline_norm: str = ""     # YYYY-MM-DD
    dday: Optional[int] = None  # 남은 일수(D-day)

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------ 공통 유틸 ------------------
def first_text_css(scope, selectors: List[str], default: str = "") -> str:
    for sel in selectors:
        try:
            t = scope.find_element(By.CSS_SELECTOR, sel).text.strip()
            if t:
                return t
        except Exception:
            pass
    return default

def first_text_xpath(scope, xpaths: List[str], default: str = "") -> str:
    for xp in xpaths:
        try:
            t = scope.find_element(By.XPATH, xp).text.strip()
            if t:
                return t
        except Exception:
            pass
    return default

def close_popups(driver):
    """쿠키/공지/레이어 팝업 닫기(있을 때만 시도)."""
    for by, sel in [
        (By.XPATH, "//button[contains(.,'동의') or contains(.,'확인') or contains(.,'닫기')]"),
        (By.CSS_SELECTOR, "button#close,.btnClose,.layerClose,.close,.btn-close"),
    ]:
        try:
            for el in driver.find_elements(by, sel)[:3]:
                try:
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.2)
                except Exception:
                    pass
        except Exception:
            pass

def smart_text(driver, el) -> str:
    """표시 텍스트를 innerText 우선으로 취득(React/line-clamp 대응)."""
    try:
        t = driver.execute_script("return arguments[0].innerText;", el) or ""
        t = t.strip()
        if t:
            return t
    except Exception:
        pass
    try:
        t = (el.get_attribute("innerText") or "").strip()
        if t:
            return t
    except Exception:
        pass
    try:
        return (el.text or "").strip()
    except Exception:
        return ""


# ------------------ 마감 텍스트 추출/정규화 ------------------
def extract_deadline_text(scope) -> str:
    """
    카드(scope) 안에서 마감 정보를 찾아 반환.
    - 날짜(우선): '09/07(토)', '08.31', '8월 30일', '2025.01.15' 등
    - 그 외: 'D-3', '오늘마감', '상시채용' 등
    """
    candidates = []
    for sel in [
        "[class*='dday']", "[class*='Dday']", "[class*='deadline']",
        "[class*='badge']", "[class*='chip']",
        "button", "span", "em", "strong"
    ]:
        try:
            for el in scope.find_elements(By.CSS_SELECTOR, sel):
                txt = (el.text or "").strip()
                if txt:
                    candidates.append(txt)
        except Exception:
            pass
    try:
        all_text = (scope.text or "").strip()
        if all_text:
            candidates.append(all_text)
    except Exception:
        pass

    # 날짜 형식 우선 탐색
    date_res = [
        re.compile(r"\b20\d{2}\.\d{1,2}\.\d{1,2}\b"),
        re.compile(r"\b\d{1,2}[./]\d{1,2}\s*\([^)]+\)"),
        re.compile(r"\b\d{1,2}[./]\d{1,2}\b"),
        re.compile(r"\b\d{1,2}\s*월\s*\d{1,2}\s*일\b"),
        re.compile(r"[~\-]\s*\d{1,2}[./]\d{1,2}\s*\([^)]+\)"),
    ]
    for txt in candidates:
        compact = txt.replace(" ", "")
        for rx in date_res:
            m = rx.search(compact)
            if m:
                return m.group(0).lstrip("~-")

    # 그 외(D-day/오늘/내일/상시)
    rx = re.compile(r"(D\s*[-+]\s*\d+)|(오늘마감|내일마감)|(상시채용|채용시까지)")
    for txt in candidates:
        m = rx.search(txt.replace(" ", ""))
        if m:
            return m.group(0)
    return ""

def normalize_deadline(deadline_text: str) -> Tuple[str, Optional[int]]:
    """
    입력(날짜/D-day/문구) → (YYYY-MM-DD 또는 '', dday 또는 None)
    """
    if not deadline_text:
        return "", None

    raw = deadline_text.strip()
    # 괄호(요일) 제거 & 공백 제거
    s = re.sub(r"\([^)]*\)", "", raw).replace(" ", "")

    # 이미 D-숫자
    m = re.search(r"D\s*[-+]\s*(\d+)", s, re.I)
    if m:
        return "", int(m.group(1))

    # 오늘/내일
    if "오늘" in s:
        return "", 0
    if "내일" in s:
        return "", 1

    # 상시/채용시까지
    if ("상시채용" in s) or ("채용시까지" in s):
        return "", None

    # 날짜 파싱
    s2 = s.replace("/", ".")
    now = time.localtime()
    today_ts = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))

    y = None; mm = None; dd = None
    explicit_year = False

    # YYYY.MM.DD
    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", s2)
    if m:
        y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        explicit_year = True
    else:
        # YY.MM.DD
        m = re.search(r"(^|[^0-9])(\d{2})\.(\d{1,2})\.(\d{1,2})", s2)
        if m:
            y, mm, dd = 2000 + int(m.group(2)), int(m.group(3)), int(m.group(4))
            explicit_year = True
        else:
            # MM.DD
            m = re.search(r"(\d{1,2})\.(\d{1,2})", s2)
            if m:
                mm, dd = int(m.group(1)), int(m.group(2))
                y = now.tm_year
                explicit_year = False
            else:
                # '8월 30일'
                m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", raw)
                if m:
                    mm, dd = int(m.group(1)), int(m.group(2))
                    y = now.tm_year
                    explicit_year = False

    if y is None or mm is None or dd is None:
        return "", None

    # 범위 보정
    mm = max(1, min(12, mm))
    dd = max(1, min(calendar.monthrange(y, mm)[1], dd))

    norm = f"{y:04d}-{mm:02d}-{dd:02d}"
    try:
        cand_ts = time.mktime(time.strptime(norm, "%Y-%m-%d"))
        # 연도 없는 표기인데 이미 지났다면 내년으로 넘김
        if (not explicit_year) and cand_ts < today_ts:
            y += 1
            norm = f"{y:04d}-{mm:02d}-{dd:02d}"
            cand_ts = time.mktime(time.strptime(norm, "%Y-%m-%d"))
        dday = int((cand_ts - today_ts) / 86400)
    except Exception:
        dday = None

    return norm, dday


# ------------------ 회사/제목/지역 탐색 ------------------
def sanitize_company(name: str) -> str:
    """회사명 끝의 '로고/기업로고/logo' 꼬리 제거."""
    if not name: return name
    name = re.sub(r"\s*(기업\s*)?로고$", "", name, flags=re.I)
    name = re.sub(r"\s*logo$", "", name, flags=re.I)
    return name.strip(" -∙·•—|")

def find_company_text(driver, base) -> str:
    """
    base(카드/앵커) 주변에서 회사명 탐색
    """
    sels = [
        ".//a[contains(@href,'/Company/')][normalize-space()][1]",
        ".//*[@role='label'][normalize-space()][1]",
        ".//*[contains(@class,'company')][normalize-space()][1]",
        ".//*[contains(@class,'coName')]//a[normalize-space()][1]",
        ".//*[contains(@class,'corpName')][normalize-space()][1]",
    ]
    node = base
    for _ in range(10):
        for xp in sels:
            try:
                el = node.find_element(By.XPATH, xp)
                t = smart_text(driver, el)
                if t:
                    return sanitize_company(t)
            except Exception:
                pass
        # 로고 alt
        try:
            img = node.find_element(By.XPATH, ".//img[@alt and normalize-space(@alt)!=''][1]")
            alt = (img.get_attribute("alt") or "").strip()
            if alt:
                return sanitize_company(alt)
        except Exception:
            pass
        # 조상으로 한 단계
        try:
            node = node.find_element(By.XPATH, "..")
        except Exception:
            break
    return ""

def find_title_text(driver, scope, anchor, company_hint: str = "") -> str:
    """공고명(제목) 추출."""
    t = smart_text(driver, anchor)
    if len(t) >= 2:
        return t

    al = (anchor.get_attribute("aria-label") or "").strip()
    if len(al) >= 2:
        return al

    try:
        parts = []
        for el in anchor.find_elements(By.XPATH, ".//span|.//em|.//strong"):
            s = smart_text(driver, el)
            if s: parts.append(s)
        txt = " ".join(parts).strip()
        if len(txt) >= 2:
            return txt
    except Exception:
        pass

    whole = smart_text(driver, scope)
    lines = [ln.strip() for ln in whole.splitlines() if ln.strip()]

    def is_badge(s: str) -> bool:
        return bool(re.search(r"(조회수|오늘마감|내일마감|상시채용|채용시까지|즉시지원|원클릭|관심기업|D\s*[-+]\s*\d+)", s))
    loc_kw = r"(서울|경기|인천|부산|대구|대전|광주|세종|울산|강원|충북|충남|전북|전남|경북|경남|제주)"
    title_kw = re.compile(r"(채용|모집|공고|정규|계약|인턴|엔지니어|개발|연구원|데이터|AI|SW|Python|파이썬|백엔드|프론트)", re.I)

    cands = []
    for ln in lines:
        if is_badge(ln): continue
        if re.search(loc_kw, ln): continue
        if company_hint and ln == company_hint: continue
        cands.append(ln)

    for ln in cands:
        if title_kw.search(ln):
            return ln
    if cands:
        return max(cands, key=len)
    return "제목 없음"


# ------------------ 드라이버 ------------------
def build_driver(gui: bool = False) -> wb.Chrome:
    """
    서버 배포 기본값: gui=False(헤드리스), 자동 종료를 전제로 사용.
    """
    opts = wb.ChromeOptions()
    if gui:
        opts.add_argument("--start-maximized")
    else:
        opts.add_argument("--headless=new")
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.page_load_strategy = "eager"

    tmp = tempfile.mkdtemp(prefix="selenium_jobkorea_")
    opts.add_argument(f"--user-data-dir={tmp}")
    atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

    driver = wb.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(20)
    return driver


# ------------------ 검색/대기 ------------------
def goto_search_with_params(driver, keyword: str, page: int = 1, latest: bool = True, newbie: bool = True):
    """잡코리아 검색 결과로 바로 이동."""
    base = "https://www.jobkorea.co.kr/Search/"
    params = {"stext": keyword, "tabType": "recruit", "page": str(page)}
    if latest:
        params["ord"] = "EditDtDesc"
    if newbie:
        params["careerType"] = "1"
    driver.get(base + "?" + urlencode(params))

def wait_results(driver, min_links: int = 5, timeout: float = 10.0) -> bool:
    """GI_Read 앵커가 충분히 로드될 때까지 폴링."""
    end = time.time() + timeout
    selectors = [
        "a[href*='/Recruit/GI_Read/']",
        "div a[href*='GI_Read']",
        "li a[href*='GI_Read']",
        "article a[href*='GI_Read']",
    ]
    last = -1
    while time.time() < end:
        count = 0
        for sel in selectors:
            try:
                count = max(count, len(driver.find_elements(By.CSS_SELECTOR, sel)))
            except Exception:
                pass
        driver.execute_script("window.scrollTo(0, 0);")
        if count >= min_links:
            return True
        if count != last:
            last = count
        time.sleep(0.05)
    return False


# ------------------ 경력 텍스트 추출 ------------------
def extract_career_text(driver, scope) -> str:
    """
    카드(scope)에서 '경력' 관련 텍스트를 찾아 반환.
    - 예: '신입', '경력 3년', '경력 1~3년', '신입·경력', '경력무관', '인턴'
    """
    # 1) 관련 클래스/태그 우선
    for sel in [
        "[class*='career']", "[class*='exp']", "[class*='경력']",
        "span", "em", "strong"
    ]:
        try:
            for el in scope.find_elements(By.CSS_SELECTOR, sel):
                t = (el.text or "").strip()
                if not t:
                    continue
                if re.search(r"(신입|경력|경력무관|인턴)", t):
                    if len(t) <= 30:
                        return t
        except Exception:
            pass

    # 2) 전체 텍스트에서 패턴 탐색
    try:
        whole = smart_text(driver, scope)
    except Exception:
        whole = (scope.text or "")
    lines = [ln.strip() for ln in (whole or "").splitlines() if ln.strip()]

    rx = re.compile(
        r"(신입(?:·경력|/경력)?|경력무관|인턴|"
        r"경력\s*\d+\s*년(?:\s*이상)?|"
        r"경력\s*\d+\s*~\s*\d+\s*년|"
        r"\d+\s*~\s*\d+\s*년\s*경력|"
        r"\d+\s*년\s*이상\s*경력)",
        re.I
    )
    cands = []
    for ln in lines:
        m = rx.search(ln.replace("경 력", "경력"))
        if m:
            cands.append(m.group(0).strip())
    if cands:
        return sorted(cands, key=len)[0]
    return ""


# ------------------ 리스트 수집(제목/회사/지역/마감/경력) ------------------
def collect_from_list(driver, want: int) -> List[Job]:
    jobs: List[Job] = []
    seen = set()

    anchors = []
    for sel in [
        "a[href*='/Recruit/GI_Read/']",
        "div a[href*='GI_Read']",
        "li a[href*='GI_Read']",
        "article a[href*='GI_Read']",
    ]:
        try:
            anchors.extend(driver.find_elements(By.CSS_SELECTOR, sel))
        except Exception:
            pass

    uniq = []
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            if "/Recruit/GI_Read/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            uniq.append(a)
        except Exception:
            continue

    for a in uniq:
        if len(jobs) >= want:
            break
        try:
            href = a.get_attribute("href")

            # 카드 scope: 가장 가까운 li/article/div
            scope = a
            for _ in range(8):
                try:
                    parent = scope.find_element(By.XPATH, "ancestor::*[self::li or self::article or self::div][1]")
                    scope = parent
                    if scope.text and len(scope.text) > 40:
                        break
                except Exception:
                    break

            # 회사명
            company = find_company_text(driver, scope) or find_company_text(driver, a)
            if not company:
                company = "회사 미상"

            # 공고명
            title = find_title_text(driver, scope, a, company_hint=company)

            # 지역
            location = first_text_css(scope, [
                "[class*='workplace']", "[class*='loc']", "[class*='area']",
                "[class*='region']", "[class*='지역']",
            ], "")
            if not location:
                try:
                    lines = [s.strip() for s in smart_text(driver, scope).splitlines() if s.strip()]
                    location = next((ln for ln in lines if re.search(r"(서울|경기|인천|부산|대구|대전|광주|세종|울산|강원|충북|충남|전북|전남|경북|경남|제주)", ln)), "")
                except Exception:
                    pass

            # 경력
            career = extract_career_text(driver, scope)
            if not career and "careerType=1" in (driver.current_url or ""):
                career = "신입(필터)"

            # 마감 텍스트 → 정규화 → D-day
            deadline = extract_deadline_text(scope)
            deadline_norm, dday = normalize_deadline(deadline)

            jobs.append(Job(
                title=title or "제목 없음",
                company=company,
                url=href,
                location=location,
                deadline=deadline,
                deadline_norm=deadline_norm,
                dday=dday,
                career=career
            ))

            time.sleep(0.05 + random.random() * 0.05)
        except Exception:
            continue

    return jobs


# ------------------ 공통 코어 & 모드별 함수 ------------------
def _crawl_core(
    keyword: str,
    want: int = 20,
    gui: bool = False,
    keep_open: bool = False,
    *,
    latest: bool = True,
    newbie: bool = True,
) -> Tuple[List[Job], Optional[wb.Chrome]]:
    driver = build_driver(gui=gui)
    wait = WebDriverWait(driver, 12)
    out: List[Job] = []
    page = 1

    while len(out) < want:
        goto_search_with_params(driver, keyword, page=page, latest=latest, newbie=newbie)
        close_popups(driver)

        try:
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "form#AKCFrm input#stext, form#AKCFrm input[name='stext']")
            ))
        except Exception:
            pass

        if not wait_results(driver, min_links=3, timeout=8):
            driver.refresh()
            close_popups(driver)
            if not wait_results(driver, min_links=3, timeout=8):
                break

        out.extend(collect_from_list(driver, want - len(out)))

        if len(out) >= want:
            break
        page += 1

    if keep_open:
        return out, driver
    else:
        driver.quit()
        return out, None


def crawl_latest_newbie(keyword: str, want: int = 20, gui: bool = False, keep_open: bool = False) -> List[Job]:
    """신입 필터 ON + 최신업데이트순"""
    items, drv = _crawl_core(keyword, want, gui, keep_open, latest=True, newbie=True)
    if drv: drv.quit()
    return items


def crawl_latest_all(keyword: str, want: int = 20, gui: bool = False, keep_open: bool = False) -> List[Job]:
    """신입 필터 OFF + 최신업데이트순"""
    items, drv = _crawl_core(keyword, want, gui, keep_open, latest=True, newbie=False)
    if drv: drv.quit()
    return items


# ------------------ 서버용: 고수준 편의 함수 ------------------
def _filter_by_dday(jobs: Iterable[Job], dday_within: Optional[int]) -> List[Job]:
    if dday_within is None:
        return list(jobs)
    out: List[Job] = []
    for j in jobs:
        if j.dday is None:
            continue
        if j.dday <= dday_within:
            out.append(j)
    return out


def search_jobs(
    keyword: str,
    *,
    limit: int = 20,
    newbie_only: bool = False,
    dday_within: Optional[int] = None,
    as_dict: bool = True,
) -> List[dict] | List[Job]:
    """
    서버(웹폼)에서 바로 호출하기 위한 통합 함수.

    Args:
        keyword: 검색 키워드
        limit: 수집 개수
        newbie_only: True면 '신입/경력무관 공고만 보기' 체크와 유사 (careerType=1)
        dday_within: D-이내 필터 (예: 7 -> D-7 이내 공고만)
        as_dict: True면 list[dict]로 반환 (JSON 직렬화 편의)

    Returns:
        list[Job] 또는 list[dict]
    """
    if newbie_only:
        items = crawl_latest_newbie(keyword=keyword, want=limit, gui=False, keep_open=False)
    else:
        items = crawl_latest_all(keyword=keyword, want=limit, gui=False, keep_open=False)

    items = _filter_by_dday(items, dday_within)
    if as_dict:
        return [it.to_dict() for it in items]
    return items


# ------------------ 유틸: D-day 포맷 (옵션) ------------------
def dday_with_abs_date(dday: Optional[int], norm: str) -> str:
    """D-n (YYYY-MM-DD) 형태로 표기. norm 없으면 dday로 계산."""
    if dday is None:
        return "-"
    if norm:
        return f"D-{dday} ({norm})"
    target = date.today() + timedelta(days=dday)
    return f"D-{dday} ({target.strftime('%Y-%m-%d')})"
