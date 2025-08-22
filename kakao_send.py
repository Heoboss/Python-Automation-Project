# kakao_send.py
import json
import requests
import os
from textwrap import shorten

KAKAO_TOKEN_PATH = os.getenv("KAKAO_TOKEN_PATH", "/home/ubuntu/aws_test1/kakaotalk.json")
KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TOKEN_INFO_URL = "https://kapi.kakao.com/v1/user/access_token_info"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")           
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", None)    

# ---------- 토큰 유틸 ----------

def _load_tokens() -> dict:
    if not os.path.exists(KAKAO_TOKEN_PATH):
        raise FileNotFoundError(f"Kakao token file not found: {KAKAO_TOKEN_PATH}")
    with open(KAKAO_TOKEN_PATH, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if "access_token" not in data:
        raise RuntimeError("access_token not found in kakao token json.")
    return data

def _save_tokens(tokens: dict):
    with open(KAKAO_TOKEN_PATH, "w", encoding="utf-8") as fp:
        json.dump(tokens, fp, ensure_ascii=False, indent=2)

def _check_token(access_token: str) -> bool:
    try:
        res = requests.get(
            KAKAO_TOKEN_INFO_URL,
            headers={"Authorization": "Bearer " + access_token},
            timeout=5,
        )
        return res.status_code == 200
    except requests.RequestException:
        return False

def _refresh_access_token(tokens: dict) -> dict:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("refresh_token is missing. Re-authorize Kakao app to get a new token.")

    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_API_KEY,
        "refresh_token": refresh_token,
    }
    if KAKAO_CLIENT_SECRET:
        data["client_secret"] = KAKAO_CLIENT_SECRET

    res = requests.post(KAKAO_TOKEN_URL, data=data, timeout=5)
    res.raise_for_status()
    new_tokens = res.json()

    if "access_token" in new_tokens:
        tokens["access_token"] = new_tokens["access_token"]
    if "refresh_token" in new_tokens:
        tokens["refresh_token"] = new_tokens["refresh_token"]
    for k in ("token_type", "expires_in", "scope", "refresh_token_expires_in"):
        if k in new_tokens:
            tokens[k] = new_tokens[k]

    _save_tokens(tokens)
    return tokens

def _get_valid_access_token() -> str:
    tokens = _load_tokens()
    at = tokens["access_token"]
    if _check_token(at):
        return at
    if not KAKAO_REST_API_KEY:
        raise RuntimeError("KAKAO_REST_API_KEY env is not set. Cannot refresh token.")
    tokens = _refresh_access_token(tokens)
    return tokens["access_token"]

# ---------- 전송 ----------

def send_to_me_text(text: str, web_url: str = None) -> dict:
    try:
        access_token = _get_valid_access_token()
    except Exception as e:
        return {"error": "token_error", "detail": str(e), "hint": f"Check {KAKAO_TOKEN_PATH}"}

    headers = {"Authorization": "Bearer " + access_token}
    
    # 텍스트 길이 제한(2000자)을 넘지 않도록 처리합니다.
    if len(text) > 1900:
        safe_text = text[:1900] + "\n...(이하 생략)..."
    else:
        safe_text = text

    template = {
        "object_type": "text",
        "text": safe_text, 
        "link": {"web_url": web_url or "https://www.kakao.com"},
    }
    data = {"template_object": json.dumps(template, ensure_ascii=False)}

    try:
        res = requests.post(KAKAO_MEMO_URL, headers=headers, data=data, timeout=8)
        if res.status_code == 401:
            try:
                tokens = _refresh_access_token(_load_tokens())
                headers["Authorization"] = "Bearer " + tokens["access_token"]
                res = requests.post(KAKAO_MEMO_URL, headers=headers, data=data, timeout=8)
            except Exception as inner:
                return {"error": "unauthorized", "detail": str(inner), "body": res.text}
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        return {"error": "request_failed", "detail": str(e)}
    except Exception as e:
        return {"error": "unknown", "detail": str(e)}

# ---------- 메시지 포맷 ----------

def _fmt_header(keyword: str, start: int, end: int) -> str:
    """메시지 헤더 포맷"""
    return f"🔔 [{keyword}] 채용 소식 {start}~{end}\n"

def _fmt_job(idx: int, p: dict) -> str:
    """한 공고를 최종 포맷에 맞춰 보기 좋게 꾸며서 반환"""
    title_raw = p.get("title") or p.get("position") or "제목 없음"
    # 긴 제목만 자르기
    title = shorten(title_raw, width=45, placeholder="…")
    
    company = p.get("company") or p.get("name") or "회사 미상"
    career = p.get("career") or p.get("experience") or ""
    loc = p.get("location") or ""
    ddl = p.get("deadline") or p.get("due") or ""
    link = p.get("link") or p.get("url") or ""

    meta_parts = [company, loc, career, ddl]
    meta = " · ".join(part for part in meta_parts if part)

    lines = []
    # [서식 수정] 불필요한 * 문자를 제거
    lines.append(f"{idx}. {title}")
    if meta:
        lines.append(f"ㆍ{meta}")
    if link:
        lines.append(f"🔗 링크: {link}")

    return "\n".join(lines)

def send_jobposts_to_kakao(keyword: str, posts: list, batch_size: int = 4):
    """크롤링 결과를 최종 포맷의 텍스트 템플릿으로 나눠서 전송"""
    if not posts:
        return {"status": "no_posts", "sent": 0}

    sent_batches = 0
    total_posts = len(posts)

    for i in range(0, total_posts, batch_size):
        batch = posts[i:i + batch_size]

        segments = [_fmt_header(keyword, i + 1, i + len(batch))]

        for idx, p in enumerate(batch, start=i + 1):
            segments.append(_fmt_job(idx, p))
            segments.append("")

        text_content = "\n".join(segments).strip()

        first_link = next(
            (p.get("link") or p.get("url") for p in batch if p.get("link") or p.get("url")),
            None
        )

        r = send_to_me_text(text_content, web_url=first_link)
        
        if isinstance(r, dict) and r.get("result_code") == 0:
            sent_batches += 1
        else:
            print("[KAKAO SEND ERROR]", r)

    return {"status": "ok", "sent_batches": sent_batches}
