# kakao_send.py
import json
import requests
import os
from textwrap import shorten

KAKAO_TOKEN_PATH = os.getenv("KAKAO_TOKEN_PATH", "/home/ubuntu/aws_ec2/kakaotalk.json")
KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TOKEN_INFO_URL = "https://kapi.kakao.com/v1/user/access_token_info"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")           # 필수
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", None)    # 쓰는 경우만

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
    safe_text = shorten(text, width=1000, placeholder="…")

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
    # 헤더와 구분선, 그리고 한 줄 공백
    return f"🔔 [{keyword}] 채용 소식 {start}~{end}\n{'='*30}\n"

def _fmt_job(idx: int, p: dict) -> str:
    """한 공고를 보기 좋게 꾸며서 반환 (URL은 단독 줄, 앞뒤 빈 줄)"""
    title   = p.get("title") or p.get("position") or "제목 없음"
    company = p.get("company") or p.get("name") or "회사 미상"
    career  = p.get("career") or p.get("experience") or ""
    loc     = p.get("location") or ""
    ddl     = p.get("deadline") or p.get("due") or ""
    link    = p.get("link") or p.get("url") or ""

    title_short = shorten(title, width=45, placeholder="…")

    meta_parts = [company]
    if loc:    meta_parts.append(loc)
    if career: meta_parts.append(career)
    if ddl:    meta_parts.append(ddl)
    meta = " · ".join(meta_parts)

    lines = [f"{idx}. {title_short}"]
    if meta:
        lines.append(f"   {meta}")

    # 링크는 단독 라인 + 앞뒤 빈 줄
    if link:
        lines.append("")               # (빈 줄) 링크 앞
        lines.append("   🔗 상세 링크")
        lines.append(link)             # URL 단독 줄
        lines.append("")               # (빈 줄) 링크 뒤

    return "\n".join(lines)

def send_jobposts_to_kakao(keyword: str, posts: list, batch_size: int = 4):
    """크롤링 결과(posts)를 카카오톡으로 나눠서 전송"""
    if not posts:
        return {"status": "no_posts", "sent": 0}

    sent = 0
    for i in range(0, len(posts), batch_size):
        batch = posts[i:i + batch_size]

        # 헤더 + 공고들
        segments = [_fmt_header(keyword, i+1, i+len(batch))]
        for idx, p in enumerate(batch, start=i+1):
            segments.append(_fmt_job(idx, p))
            segments.append("")  # 공고 간 빈 줄

        # 마지막에 구분선으로 마무리
        segments.append("="*30)

        text = "\n".join(segments).rstrip()

        # 미리보기용 링크(첫 번째 유효 URL)
        first_link = next(
            (p.get("link") or p.get("url") for p in batch if (p.get("link") or p.get("url"))),
            None
        )

        r = send_to_me_text(text, web_url=first_link)
        if isinstance(r, dict) and r.get("result_code") == 0:
            sent += 1
        else:
            print("[KAKAO SEND ERROR]", r)

    return {"status": "ok", "sent": sent}
