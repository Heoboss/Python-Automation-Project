# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages
import json
import os
import traceback
import threading
from datetime import datetime, timedelta
from scraper import *
from inflearn_scraper import scrape_inflearn
from news_scraper import scrape_nate_news
from finance_api import (
    find_crno_by_name,
    fetch_all_fin_summary_by_crno,
    fetch_company_outline,
    fmt_date8,
    comma,
    build_chart_bundle,
)
import re
from typing import List, Dict
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from jk_crawler import search_jobs as jk_search_jobs
import concurrent.futures

if not os.path.exists("static"):
    os.mkdir("static")
if not os.path.exists("templates"):
    os.mkdir("templates")

USER_FILE = "users.json"
CACHE_DIR = "cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key-for-flash")

def load_users():
    if not os.path.exists(USER_FILE) or os.path.getsize(USER_FILE) == 0:
        return {}
    try:
        with open(USER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_users(users):
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)


@app.route("/")
def index():
    if 'user' in request.cookies:
        return redirect(url_for('main_page'))
    # 다른 곳에서 넘어온 이전 flash 메시지 제거
    get_flashed_messages()
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    login_id = request.form["login_id"]
    login_pw = request.form["login_pw"]
    users = load_users()
    if login_id in users and users[login_id] == login_pw:
        response = redirect(url_for('main_page'))
        response.set_cookie("user", login_id, httponly=True, samesite="Lax")
        return response
    else:
        flash('아이디 또는 비밀번호가 일치하지 않습니다.')
        return redirect(url_for('index'))

@app.route("/logout")
def logout():
    response = redirect(url_for('index'))
    response.delete_cookie('user')
    return response

@app.route("/signup")
def signup_page():
    return render_template("signup.html")

@app.route("/register", methods=["POST"])
def register():
    user_id = request.form["user_id"]
    user_pw = request.form["user_pw"]
    if not user_id or not user_pw:
        flash('아이디와 비밀번호를 모두 입력해주세요.')
        return redirect(url_for('signup_page'))
    users = load_users()
    if user_id in users:
        flash('이미 존재하는 아이디입니다.')
        return redirect(url_for('signup_page'))
    users[user_id] = user_pw
    save_users(users)
    flash('회원가입이 완료되었습니다. 로그인해주세요.')
    return redirect(url_for('index'))

# 서비스 라우팅
@app.route("/main")
def main_page():
    login_id = request.cookies.get('user')
    if login_id:
        return render_template("main.html", username=login_id)
    else:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))

@app.route("/crawler")
def crawler_page():
    login_id = request.cookies.get('user')
    if login_id:
        return render_template("crawler_input.html", username=login_id, active_page = 'crawler')
    else:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
    
@app.route("/start_scrape")
def start_scrape():
    login_id = request.cookies.get('user')
    if 'user' not in request.cookies:
        return redirect(url_for('index'))
    keyword = request.args.get("keyword")
    count = request.args.get("count")
    if not keyword or not count:
        flash("키워드와 개수를 모두 입력해주세요.")
        return redirect(url_for('crawler_page'))
    return render_template("crawler_loading.html", keyword=keyword, count=count, username=login_id)

@app.route("/scrape")
def scrape():
    login_id = request.cookies.get('user')
    if not login_id:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))

    keyword = request.args.get("keyword")
    count_str = request.args.get("count")

    try:
        count = int(count_str)
        if count <= 0: raise ValueError
    except (ValueError, TypeError):
        flash("개수는 1 이상의 숫자여야 합니다.")
        return redirect(url_for('crawler_page'))

    safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword)
    cache_filename = os.path.join(CACHE_DIR, f"{login_id}_{safe_keyword}_{count}.json")
    cache_lifetime = timedelta(minutes=15)

    if os.path.exists(cache_filename):
        mod_time = os.path.getmtime(cache_filename)
        age = datetime.now() - datetime.fromtimestamp(mod_time)
        if age < cache_lifetime:
            print(f"Loading results from user cache: {cache_filename}")
            with open(cache_filename, "r", encoding="utf-8") as f:
                scraped_results = json.load(f)
            return render_template("crawler_result.html", keyword=keyword, 
                                     results=scraped_results, from_cache=True, 
                                     count=count,active_page='crawler', username=login_id)

    # 스레딩으로 동시 크롤링 실행
    try:
        print(f"No valid cache for user '{login_id}'. Starting new concurrent scrape for '{keyword}'.")
        combined_results = {
            "jobplanet": [],
            "jobkorea": [],
            "incruit": []
        }

        # ThreadPoolExecutor를 사용하여 각 함수를 별도의 스레드에서 동시에 실행
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 각 크롤링 함수를 executor에 제출(submit)하여 작업을 시작
            future_jp = executor.submit(scrape_jobplanet, keyword, count)
            future_jk = executor.submit(scrape_jobkorea_simple, keyword, count)
            future_ic = executor.submit(scrape_incruit, keyword, count)
            
            # 각 작업(future)이 완료되면 결과를 가져와 딕셔너리에 저장
            # .result()는 해당 작업이 끝날 때까지 기다렸다가 결과값을 반환합니다.
            combined_results["jobplanet"] = future_jp.result()
            combined_results["jobkorea"] = future_jk.result()
            combined_results["incruit"] = future_ic.result()

        # 3개 사이트 모두에서 결과가 하나도 없는지 확인
        if not any(combined_results.values()):
            flash(f"'{keyword}'에 대한 검색 결과가 없습니다.")
            return redirect(url_for('crawler_page'))

        # 캐시 파일 저장
        with open(cache_filename, "w", encoding="utf-8") as f:
            json.dump(combined_results, f, ensure_ascii=False, indent=4)
            print(f"Saved new combined results to user cache: {cache_filename}")
            
        return render_template("crawler_result.html", keyword=keyword, results=combined_results,
                                 from_cache=False, count=count, username=login_id)

    except Exception as e:
        print(f"An error occurred during concurrent scraping: {e}")
        flash(f"동시 크롤링 중 오류가 발생했습니다: {e}")
        return redirect(url_for('crawler_page'))

@app.route("/clear_cache")
def clear_cache():
    login_id = request.cookies.get('user')
    if not login_id:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
    keyword = request.args.get("keyword")
    count_str = request.args.get("count")
    if not keyword or not count_str:
        return redirect(url_for('crawler_page'))
    try:
        safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword)
        cache_filename = os.path.join(CACHE_DIR, f"{login_id}_{safe_keyword}_{count_str}.json")
        if os.path.exists(cache_filename):
            os.remove(cache_filename)
            flash(f"'{keyword}'에 대한 캐시가 성공적으로 삭제되었습니다.")
            app.logger.info(f"Cache file deleted by user '{login_id}': {cache_filename}")
        else:
            flash("삭제할 캐시 파일이 존재하지 않습니다.")
    except Exception as e:
        app.logger.exception("Error deleting cache file")
        flash(f"캐시 삭제 중 오류가 발생했습니다: {e}")
    return redirect(url_for('crawler_page'))

@app.route("/job_detail")
def job_detail():
    login_id = request.cookies.get('user')
    if not login_id:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
    keyword = request.args.get("keyword")
    count = request.args.get("count")
    job_index_str = request.args.get("job_index")
    if not all([keyword, count, job_index_str]):
        flash("잘못된 접근입니다.")
        return redirect(url_for('crawler_page'))
    try:
        job_index = int(job_index_str)
        safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword)
        cache_filename = os.path.join(CACHE_DIR, f"{login_id}_{safe_keyword}_{count}.json")
        if os.path.exists(cache_filename):
            with open(cache_filename, "r", encoding="utf-8") as f:
                all_results = json.load(f)
            
            # (핵심 수정) 전체 결과(딕셔너리)에서 'jobplanet' 리스트를 추출합니다.
            jobplanet_results = all_results.get("jobplanet", [])
            
            if 0 <= job_index < len(jobplanet_results):
                job_data = jobplanet_results[job_index]
                return render_template("job_detail.html", job=job_data, keyword=keyword, count=count, username=login_id)
            else:
                flash("해당 채용 공고를 찾을 수 없습니다.")
                return redirect(url_for('crawler_page'))
        else:
            flash("세션이 만료되었거나 캐시된 데이터가 없습니다. 다시 검색해주세요.")
            return redirect(url_for('crawler_page'))
    except (ValueError, IndexError, KeyError) as e:
        app.logger.exception("상세 페이지 접근 오류")
        flash("잘못된 요청입니다.")
        return redirect(url_for('crawler_page'))
    
# ---------------------- << 기업정보 >> ----------------------
@app.route("/finance")
def finance_page():
    login_id = request.cookies.get('user')
    if login_id:
        return render_template("finance_input.html", active_page='finance', username=login_id)
    else:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
    

@app.route("/get_finance_data", methods=["POST"])
def get_finance_data():
    login_id = request.cookies.get('user')
    if 'user' not in request.cookies:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))

    company_name = request.form.get("company_name")
    if not company_name:
        flash("기업명을 입력해주세요.")
        return redirect(url_for('finance_page'))

    try:
        # 1) 회사명 → crno
        crno = find_crno_by_name(company_name)
        if not crno:
            flash(f"'{company_name}'에 해당하는 기업을 찾을 수 없습니다. 정확한 기업명을 입력해주세요.")
            return redirect(url_for('finance_page'))

        # 2) crno → 요약재무 전건
        finance_data = fetch_all_fin_summary_by_crno(crno)

        # 3) 회사명 → 기업기본정보
        outline_list = fetch_company_outline(company_name, page_no=1, num_rows=20, strict=True)
        outline = outline_list[0] if outline_list else None

        # 4) 그래프 데이터 패키지
        chart_bundle = build_chart_bundle(finance_data)

        # 콘솔 프린트용
        def _key_fin(it):
            by = it.get("bizYear")
            try:
                by_i = int(str(by))
            except Exception:
                by_i = -1
            return (-by_i, str(it.get("basDt") or ""))

        rows_sorted = sorted(finance_data or [], key=_key_fin)

        console_fin_lines = []
        console_fin_lines.append(f"회사명 : {company_name}")
        console_fin_lines.append(f"법인등록번호 : {crno}")
        console_fin_lines.append("-" * 40)
        for idx, r in enumerate(rows_sorted, 1):
            console_fin_lines.append(f"[{idx}] ------------------------------")
            console_fin_lines.append(f"사업연도 : {r.get('bizYear', '-')}")
            console_fin_lines.append(f"기준일 : {fmt_date8(r.get('basDt'))}")
            console_fin_lines.append(f"통화 : {r.get('curCd', '-') or '-'}")
            console_fin_lines.append(f"재무구분 : {r.get('fnclDcdNm', '-') or '-'}")
            console_fin_lines.append(f"매출액 : {comma(r.get('enpSaleAmt'))}")
            console_fin_lines.append(f"영업이익 : {comma(r.get('enpBzopPft'))}")
            console_fin_lines.append(f"자산총계 : {comma(r.get('enpTastAmt'))}")
            console_fin_lines.append(f"부채총계 : {comma(r.get('enpTdbtAmt'))}")
            console_fin_lines.append(f"자본총계 : {comma(r.get('enpTcptAmt'))}")
            console_fin_lines.append("-" * 40)
        console_fin_lines.append(f"총 {len(rows_sorted)}건을 출력했습니다.")

        console_outline_lines = []
        if outline:
            console_outline_lines.append("총 1건")
            console_outline_lines.append("")
            console_outline_lines.append("[1] -------------------------------")
            PRINT_ORDER = [
                "corpNm", "enpRprFnm", "enpHmpgUrl", "enpEstbDt",
                "enpXchgLstgDt", "enpEmpeCnt", "empeAvgCnwkTermCtt", "enpPn1AvgSlryAmt",
            ]
            KOR_LABELS = {
                "corpNm": "회사명",
                "enpRprFnm": "대표자",
                "enpHmpgUrl": "홈페이지",
                "enpEstbDt": "설립일",
                "enpXchgLstgDt": "유가증권시장 상장일",
                "enpEmpeCnt": "종업원 수",
                "empeAvgCnwkTermCtt": "평균 근속연수",
                "enpPn1AvgSlryAmt": "1인당 평균 급여액",
            }
            def _fmt_date8_local(s):
                s = (s or "").strip()
                return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else (s or "-")
            def _fmt_value(key, val):
                if val in (None, "", " "):
                    return "-"
                s = str(val).strip()
                if key in ("enpEstbDt", "enpXchgLstgDt"):
                    return _fmt_date8_local(s)
                if key == "enpEmpeCnt":
                    return f"{int(s):,}명" if s.isdigit() else s
                if key == "enpPn1AvgSlryAmt":
                    return f"{int(s):,}원" if s.isdigit() else s
                return s
            for key in PRINT_ORDER:
                label = KOR_LABELS.get(key, key)
                console_outline_lines.append(f"{label}: {_fmt_value(key, outline.get(key, ''))}")

        return render_template(
            "finance_result.html",
            company_name=company_name,
            crno=crno,
            results=rows_sorted,
            outline=outline,
            console_outline_lines=console_outline_lines,
            console_fin_lines=console_fin_lines,
            fmt_date8=fmt_date8,
            comma=comma,
            chart_bundle=chart_bundle,
            active_page='finance',
            username=login_id
        )

    except Exception as e:
        app.logger.exception("재무정보 조회 중 오류")
        flash(f"데이터를 조회하는 중 오류가 발생했습니다: {e}")
        return redirect(url_for('finance_page'))

# ---------------------- << 인프런 기능 수정 >> ----------------------
@app.route("/inflearn")
def inflearn_page():
    login_id = request.cookies.get('user')
    if 'user' not in request.cookies:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
    return render_template("inflearn_input.html", active_page='inflearn', username=login_id)

@app.route("/start_search_inflearn")
def start_search_inflearn():
    login_id = request.cookies.get('user')
    if 'user' not in request.cookies:
        return redirect(url_for('index'))
    
    keyword = request.args.get("keyword")
    limit = request.args.get('limit', 10, type=int)

    if not keyword:
        flash("검색어를 입력해주세요.")
        return redirect(url_for('inflearn_page'))
        
    return render_template("inflearn_loading.html", keyword=keyword, limit=limit, username=login_id)

@app.route("/search_inflearn", methods=["GET"])
def search_inflearn():
    login_id = request.cookies.get('user')
    if 'user' not in request.cookies:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
    
    keyword = request.args.get("keyword")
    limit = request.args.get('limit', 10, type=int)

    if not keyword:
        flash("검색어를 입력해주세요.")
        return redirect(url_for('inflearn_page'))
    
    try:
        results = scrape_inflearn(keyword, limit)
        if not results:
            flash(f"'{keyword}'에 대한 검색 결과가 없습니다.")
            return redirect(url_for('inflearn_page'))
            
        return render_template("inflearn_result.html", keyword=keyword, results=results,active_page='inflearn',
                               username=login_id)
    
    except Exception as e:
        print(f"인프런 크롤링 중 서버 오류 발생: {e}")
        flash(f"데이터를 조회하는 중 오류가 발생했습니다: {e}")
        return redirect(url_for('inflearn_page'))
# ---------------------- << 인프런 기능 수정 끝 >> ----------------------
# ---------------------- << 뉴스 기능 수정 블록 시작 >> ----------------------
@app.route("/news")
def news_page():
    login_id = request.cookies.get('user')
    if 'user' not in request.cookies:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))

    keyword = request.args.get("keyword")
    page = request.args.get("page", 1, type=int)
    
    try:
        all_results = []
        if keyword:
            # ⭐️ 키워드가 있을 경우, 통합 스크래퍼 함수를 한 번만 호출합니다.
            all_results = scrape_nate_news(keyword, page)

            # ⭐️ 날짜를 기준으로 최신순 정렬
            def get_date(news_item):
                try:
                    # 'YYYY.MM.DD' 형식의 날짜를 파싱
                    return datetime.strptime(news_item.get('date', ''), '%Y.%m.%d')
                except (ValueError, TypeError):
                    # 날짜 형식이 다르거나 없는 경우 가장 오래된 날짜로 처리
                    return datetime.min

            all_results.sort(key=get_date, reverse=True)
            
        else:
            # 키워드가 없으면 네이트 최신 뉴스만 가져옴
            all_results = scrape_nate_news()
        
        if not all_results and keyword:
             flash(f"'{keyword}'에 대한 검색 결과가 없습니다.")

        return render_template("news_page.html", keyword=keyword, results=all_results, page=page, active_page='news',
                               username=login_id)

    except Exception as e:
        print(f"뉴스 크롤링 중 서버 오류 발생: {e}")
        flash("뉴스를 조회하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        return render_template("news_page.html", keyword=keyword, results=[], page=page, active_page='news',username=login_id)
# ---------------------- << 뉴스 기능 수정 블록 끝 >> ----------------------

# ---------------------- << 추가 블록: 카카오 전송/스케줄 >> ----------------------
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

PREF_FILE = "user_prefs.json"
KST = ZoneInfo("Asia/Seoul")

# 제목에 포함되면 제외할 키워드
TITLE_BLOCK_WORDS = ("취업연계", "교육", "부트캠프", "국비")
# 필요하면 나중에 ("취업연계", "교육", "부트캠프", "국비") 처럼 늘리면 됩니다.


scheduler = BackgroundScheduler(
    timezone=KST,
    job_defaults={
        "coalesce": True,          # 밀린 실행 1회로 합치기
        "max_instances": 3,
        "misfire_grace_time": 600  # 최대 10분까지 놓쳐도 실행
    }
)

def load_prefs() -> dict:
    if not os.path.exists(PREF_FILE) or os.path.getsize(PREF_FILE) == 0:
        return {}
    try:
        with open(PREF_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_prefs(prefs: dict):
    with open(PREF_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

def parse_deadline_dday(text: str) -> int:
    if not text:
        return 999
    t = text.strip()
    if "상시" in t or "채용시" in t:
        return 999
    if "오늘" in t:
        return 0
    if "내일" in t:
        return 1
    # --- 2순위: "~MM/DD" 형식의 날짜 처리 ---
    # 정규표현식으로 '월/일' 부분을 추출 (예: ~09/01(월) -> 09/01)
    date_match = re.search(r'(\d{1,2})/(\d{1,2})', t)
    if date_match:
        try:
            # 오늘 날짜 정보 가져오기 (시간은 제외)
            today = datetime.now(KST).date()
            
            # 추출한 월, 일과 현재 연도를 조합하여 마감 날짜 생성
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            year = today.year
            deadline_date = date(year, month, day)

            # 만약 계산된 마감일이 오늘보다 과거라면 (예: 현재 12월, 마감일 1월),
            # 마감일은 내년이므로 연도를 1 더해줍니다.
            if deadline_date < today:
                deadline_date = date(year + 1, month, day)
            
            # D-day 계산
            d_day = (deadline_date - today).days
            return d_day
        except ValueError:
            # 날짜 형식이 잘못된 경우 (예: 2/30) 다음 로직으로 넘어감
            pass

    # --- 3순위: "D-숫자" 형식 처리 ---
    d_day_match = re.search(r"D-(\d+)", t, re.IGNORECASE)
    if d_day_match:
        return int(d_day_match.group(1))
        
    # 모든 조건에 맞지 않으면 '상시채용'과 동일하게 처리
    return 999
    # m = re.search(r"D-(\d+)", t)
    # return int(m.group(1)) if m else 999

def filter_posts(posts: List[Dict], only_fresher=True, max_dday=7, edu_mode: str = "exclude") -> List[Dict]:
    """
    edu_mode:
      - "exclude" (기본): 제목에 TITLE_BLOCK_WORDS가 있으면 제외
      - "only"          : 제목에 TITLE_BLOCK_WORDS가 있는 것만 포함
    """
    kept = []
    for p in posts:
        title = (p.get("title") or p.get("position") or p.get("name") or "").strip()
        has_edu = bool(title and any(kw in title for kw in TITLE_BLOCK_WORDS))

        # 교육 필터
        if edu_mode == "exclude" and has_edu:
            continue
        if edu_mode == "only" and not has_edu:
            continue

        # 기존 신입/무관 필터
        exp = (p.get("experience") or p.get("career") or "")
        if only_fresher and not (("신입" in exp) or ("무관" in exp)):
            continue

        # 기존 D-day 필터
        dday = parse_deadline_dday(p.get("deadline", ""))
        if 0 <= dday <= max_dday:
            kept.append(p)
    return kept


_scrape_lock = threading.Lock()

def scrape_and_send(keyword: str, count: int, only_fresher: bool = True,
                    max_dday: int = 7, batch_size: int = 5, edu_mode: str = "exclude"):
    if not _scrape_lock.acquire(blocking=False):
        app.logger.info("scrape_and_send: another instance is running, skip")
        return {"ok": False, "sent": 0, "reason": "locked"}
    try:
        from kakao_send import send_jobposts_to_kakao
        posts = jk_search_jobs(
            keyword=keyword,
            limit=count,
            newbie_only=only_fresher,
            dday_within=None,
            as_dict=True
        )
        # /// [확인용 로그 추가 1] ///
        print(f"✅ 스크랩된 원본 공고 수: {len(posts)}개")
        
        posts = filter_posts(posts, only_fresher=only_fresher, max_dday=max_dday, edu_mode=edu_mode)
        # /// [확인용 로그 추가 2] ///
        print(f"➡️ 필터링 후 남은 공고 수: {len(posts)}개")
        if not posts:
            app.logger.info("[INFO] 보낼 공고 없음.")
            return {"ok": False, "sent": 0}
        res = send_jobposts_to_kakao(keyword, posts, batch_size=batch_size)
        app.logger.info("[INFO] 카카오 전송 완료: %s", res)
        return {"ok": True, "sent": len(posts)}
    except Exception as e:
        app.logger.exception("scrape_and_send failed")
        return {"ok": False, "sent": 0, "error": str(e)}
    finally:
        _scrape_lock.release()

# === 다음 실행 시각 문자열(KST) ===
def next_run_kst_str(login_id: str) -> str | None:
    job = scheduler.get_job(f"daily_{login_id}")
    if not job or not job.next_run_time:
        return None
    nrt = job.next_run_time
    if nrt.tzinfo is None:
        nrt = nrt.replace(tzinfo=scheduler.timezone)
    try:
        nrt_kst = nrt.astimezone(KST)
    except Exception:
        nrt_kst = nrt
    return nrt_kst.strftime("%Y-%m-%d %H:%M")

def schedule_job(login_id: str, keyword: str, count: int,
                 only_fresher: bool, max_dday: int, batch_size: int,
                 send_time: str = "09:00", edu_mode: str = "exclude"):
    job_id = f"daily_{login_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    h, m = map(int, send_time.split(":"))
    now = datetime.now(KST)
    first_run = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if first_run <= now:
        first_run += timedelta(days=1)

    trigger = CronTrigger(hour=h, minute=m, timezone=KST)
    scheduler.add_job(
        func=scrape_and_send,
        trigger=trigger,
        next_run_time=first_run,
        args=[keyword, count, only_fresher, max_dday, batch_size, edu_mode],  # ← 추가
        id=job_id,
        replace_existing=True,
        jitter=10
    )
    app.logger.info("[SCHEDULE] %s: 매일 %s '%s' 등록 (first_run=%s KST)",
                    login_id, send_time, keyword, first_run.isoformat())

# === 스케줄 상태 API (화면 갱신용) ===
@app.route("/api/schedule_status")
def api_schedule_status():
    login_id = request.cookies.get('user')
    if not login_id:
        return {"ok": False, "error": "auth"}, 401
    prefs = load_prefs().get(login_id, {})
    return {
        "ok": True,
        "enabled": bool(prefs.get("enabled")),
        "send_time": prefs.get("send_time"),
        "next_run": next_run_kst_str(login_id),
        "edu_mode": prefs.get("edu_mode", "exclude"),
    }, 200

# --- 즉시 전송 ---
@app.route("/send_kakao_now", methods=["POST", "GET"])
def send_kakao_now():
    login_id = request.cookies.get('user')
    if not login_id:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.values.get("ajax") == "1":
            return {"ok": False, "error": "auth", "message": "로그인이 필요합니다."}, 401
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))

    keyword = request.values.get("keyword", "python")
    count = int(request.values.get("count", 30))
    only_fresher = request.values.get("only_fresher", "0") in ("1", "true", "True")
    max_dday = int(request.values.get("max_dday", 7))
    batch_size = int(request.values.get("batch_size", 5))
    edu_mode = request.values.get("edu_mode", "exclude")
    
    print(f"✅ [디버그] 수신된 필터 값: max_dday={max_dday}, only_fresher={only_fresher}, edu_mode='{edu_mode}'")
    
    try:
        result = scrape_and_send(keyword, count, only_fresher, max_dday, batch_size, edu_mode)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.values.get("ajax") == "1":
            status = 200 if result.get("ok") else 400
            return {
                "ok": result.get("ok", False),
                "sent": result.get("sent", 0),
                "keyword": keyword,
                "reason": result.get("reason") or result.get("error")
            }, status

        if result.get("ok"):
            flash(f"카카오 전송 완료 (보낸 공고: {result.get('sent', 0)}건)")
        else:
            reason = result.get("reason") or result.get("error") or "알 수 없는 이유"
            flash(f"전송 건너뜀/실패: {reason}")
    except Exception as e:
        app.logger.exception("send_kakao_now failed")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.values.get("ajax") == "1":
            return {"ok": False, "error": "exception", "message": str(e)}, 500
        flash(f"전송 중 오류: {e}")

    return redirect(url_for('main_page'))

# --- 예약 저장/해제 ---
@app.route("/subscribe_kakao", methods=["POST"])
def subscribe_kakao():
    login_id = request.cookies.get('user')
    if not login_id:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"ok": False, "error": "auth", "message": "로그인이 필요합니다."}, 401
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))

    body = request.get_json(silent=True) or request.form

    keyword = body.get("keyword", "python")
    count = int(body.get("count", 30))
    only_fresher = str(body.get("only_fresher", "0")) in ("1", "true", "True")
    max_dday = int(body.get("max_dday", 7))
    batch_size = int(body.get("batch_size", 5))
    send_time = body.get("send_time", "09:00")
    enabled = str(body.get("enabled", "1")) in ("1", "true", "True")
    edu_mode = body.get("edu_mode", "exclude")

    prefs = load_prefs()
    prefs[login_id] = {
        "keyword": keyword,
        "count": count,
        "only_fresher": only_fresher,
        "max_dday": max_dday,
        "batch_size": batch_size,
        "send_time": send_time,
        "enabled": enabled,
        "edu_mode": edu_mode,
    }
    save_prefs(prefs)

    if enabled:
        schedule_job(login_id, keyword, count, only_fresher, max_dday, batch_size, send_time, edu_mode)
        msg = f"매일 {send_time} 전송 예약됨"
    else:
        job = scheduler.get_job(f"daily_{login_id}")
        if job:
            job.remove()
        msg = "자동 전송 해제됨"

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {
            "ok": True,
            "message": msg,
            "pref": {
                "keyword": keyword, "count": count, "only_fresher": only_fresher,
                "max_dday": max_dday, "batch_size": batch_size,
                "send_time": send_time, "enabled": enabled, "edu_mode": edu_mode
            },
            "next_run": next_run_kst_str(login_id) if enabled else None,
    }, 200

    flash(msg)
    return redirect(url_for('main_page'))
# ---------------------- << 추가 블록 끝 >> ----------------------

if __name__ == "__main__":
    should_start = (os.environ.get("WERKZEUG_RUN_MAIN") == "true") or (os.environ.get("WERKZEUG_RUN_MAIN") is None)
    if should_start and not scheduler.running:
        scheduler.start()
        app.logger.info("[SCHEDULER] started in this process")
    app.run(host="0.0.0.0", port=5000, use_reloader=True)