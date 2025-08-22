# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from selenium import webdriver as wb
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from datetime import datetime, timedelta
import re

def parse_date(date_str):
    """
    다양한 형식의 날짜 문자열을 datetime 객체로 변환하여 정확한 정렬을 지원합니다.
    절대적 날짜는 해당 날짜의 가장 처음(00:00:00)으로, 상대적 날짜는 현재 시각 기준으로 변환합니다.
    """
    if not isinstance(date_str, str):
        return datetime.min
    
    now = datetime.now()
    
    # 1. 상대적 시간 처리: '분 전', '시간 전', '어제', '일 전'
    if '분전' in date_str or '분 전' in date_str:
        try:
            minutes_ago = int(re.search(r'\d+', date_str).group())
            return now - timedelta(minutes=minutes_ago)
        except (ValueError, AttributeError):
            pass
    if '시간전' in date_str or '시간 전' in date_str:
        try:
            hours_ago = int(re.search(r'\d+', date_str).group())
            return now - timedelta(hours=hours_ago)
        except (ValueError, AttributeError):
            pass
    if '어제' in date_str:
        yesterday = now - timedelta(days=1)
        return yesterday.replace(hour=0, minute=0, second=0)
    if '일전' in date_str or '일 전' in date_str:
        try:
            days_ago = int(re.search(r'\d+', date_str).group())
            day = now - timedelta(days=days_ago)
            return day.replace(hour=0, minute=0, second=0)
        except (ValueError, AttributeError):
            pass

    # 2. 절대적 날짜 형식 처리: 'YYYY.MM.DD' 또는 'MM.DD'
    formats_to_try = [
        ('%Y.%m.%d %H:%M', False),
        ('%Y.%m.%d', True),
        ('%m.%d %H:%M', False)
    ]
    for fmt, is_date_only in formats_to_try:
        try:
            dt = datetime.strptime(date_str, fmt)
            if is_date_only:
                return dt.replace(hour=0, minute=0, second=0)
            return dt
        except ValueError:
            continue
            
    # 현재 연도 정보가 없는 경우 처리 (ex: 08.12)
    try:
        dt = datetime.strptime(f"{now.year}.{date_str}", '%Y.%m.%d')
        return dt.replace(hour=0, minute=0, second=0)
    except ValueError:
        return datetime.min

def scrape_nate_news(keyword=None, page=1):
    base_url = "https://news.nate.com"
    if keyword:
        url = f"{base_url}/search?q={keyword}&page={page}"
        print(f"'{keyword}' 키워드로 네이트 뉴스 검색 (페이지: {page})")
    else:
        url = f"{base_url}/section?mid=n0600"
        print("네이트 IT/과학 최신 뉴스를 가져옵니다.")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    response = requests.get(url, headers=headers)
    response.encoding = 'euc-kr'
    if response.status_code != 200:
        print(f"Error: 페이지를 가져올 수 없습니다. 상태 코드: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    nate_results = []

    if keyword:
        news_list = soup.select("ul.search-list > li.items")
        for news in news_list:
            try:
                main_article_link = news.select_one("a.thumb-wrap")
                if not main_article_link: continue
                title_tag = main_article_link.select_one("h2.tit")
                summary_tag = main_article_link.select_one("span.txt")
                time_info_tag = main_article_link.select_one("span.time")
                if title_tag and summary_tag and time_info_tag:
                    # 날짜 정보를 정규표현식으로 추출하여 안정성 확보
                    date_match = re.search(r'(\d{2}\.\d{2} \d{2}:\d{2}|.*[분|시간|일]전|어제)', time_info_tag.text)
                    date_str = date_match.group(1).strip() if date_match else "날짜 정보 없음"
                    
                    nate_results.append({
                        "title": title_tag.text.strip(),
                        "summary": summary_tag.text.strip(),
                        "press": time_info_tag.contents[0].strip(),
                        "link": main_article_link['href'],
                        "date": date_str,
                        "source": "Nate News"
                    })
            except (AttributeError, TypeError, IndexError):
                continue
        
        combined_results = nate_results
        
        sorted_results = sorted(
            combined_results, 
            key=lambda x: parse_date(x.get('date')), 
            reverse=True
        )
        return sorted_results

    else:
        news_list = soup.select("div.mduCluster, ul.mduStrongList > li")
        for news_item in news_list:
            try:
                a_tag = news_item.select_one("a")
                if not a_tag: continue
                title = a_tag.text.strip()
                link = a_tag['href']
                summary_tag = news_item.select_one("span.tb")
                summary = summary_tag.text.strip().replace(title, "").strip() if summary_tag else "요약 정보 없음"
                press_tag = news_item.select_one("span.medium")
                press = press_tag.contents[0].strip() if press_tag else "언론사 정보 없음"
                date_tag = press_tag.find("em") if press_tag else None
                date = date_tag.text.strip() if date_tag else "시간 정보 없음"
                nate_results.append({
                    "title": title, "summary": summary, "press": press,
                    "link": link, "date": date, "source": "Nate News"
                })
            except (AttributeError, TypeError, IndexError):
                continue
        
        sorted_results = sorted(nate_results, key=lambda x: parse_date(x.get('date')), reverse=True)
        return sorted_results[:5]