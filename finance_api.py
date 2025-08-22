# -*- coding: utf-8 -*-
import requests
import time
import math
import json
from typing import Optional, List, Dict, Tuple

SERVICE_KEY = "jvcIVEG7hdytqIlJiB%2BfPbqM%2B3UDfa0JUss%2BMgh6GmqlNYMuzvkyS%2BHQ%2BY1JbWChr2tgVCui%2F%2FmE5rGAXo3d4g%3D%3D"
RESULT_TYPE = "json"

OUTLINE_URL = "http://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2"
FIN_SUM_URL = "http://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2/getSummFinaStat_V2"

def req_json(url: str, params: dict) -> dict:
    full_url = f"{url}?serviceKey={SERVICE_KEY}"
    try:
        r = requests.get(full_url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        header = data.get("response", {}).get("header", {})
        code = str(header.get("resultCode", "")).strip()
        if code not in ("0", "00", "0000"):
            raise RuntimeError(f"API Error: {header.get('resultMsg', 'Unknown Error')}")
        return data
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network Error: {e}")
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON response from API.")

def find_crno_by_name(company_name: str, strict: bool = True) -> Optional[str]:
    params = {"pageNo": "1","numOfRows": "50","resultType": RESULT_TYPE,"corpNm": company_name}
    data = req_json(OUTLINE_URL, params)
    items = (data.get("response", {}).get("body", {}).get("items") or {}).get("item")
    if not items: return None
    if isinstance(items, dict): items = [items]
    if strict:
        for it in items:
            if it.get("corpNm") == company_name and it.get("crno"): return it["crno"]
    return items[0].get("crno")

def fetch_all_fin_summary_by_crno(crno: str, num_rows: int = 100, delay_sec: float = 0.2, fnclDcd: Optional[str] = None) -> List[Dict]:
    params = {"pageNo": "1","numOfRows": str(num_rows),"resultType": RESULT_TYPE,"crno": crno}
    if fnclDcd: params["fnclDcd"] = fnclDcd
    data = req_json(FIN_SUM_URL, params)
    body = data.get("response", {}).get("body", {})
    total_count = int(body.get("totalCount", 0) or 0)
    items = (body.get("items") or {}).get("item")
    if items is None: items = []
    elif isinstance(items, dict): items = [items]
    all_rows: List[Dict] = []; all_rows.extend(items)
    total_pages = math.ceil(total_count / num_rows) if num_rows else 1
    for page_no in range(2, total_pages + 1):
        time.sleep(delay_sec); params["pageNo"] = str(page_no)
        page_data = req_json(FIN_SUM_URL, params)
        page_items = (page_data.get("response", {}).get("body", {}).get("items") or {}).get("item")
        if not page_items: continue
        if isinstance(page_items, dict): page_items = [page_items]
        all_rows.extend(page_items)
    def _sort_key(item: Dict):
        try: return -int(item.get("bizYear", 0))
        except (ValueError, TypeError): return 0
    return sorted(all_rows, key=_sort_key)

def fetch_company_outline(company_name: str, page_no: int = 1, num_rows: int = 20, strict: bool = True) -> List[Dict]:
    params = {"pageNo": str(page_no),"numOfRows": str(num_rows),"resultType": RESULT_TYPE,"corpNm": company_name}
    data = req_json(OUTLINE_URL, params)
    body = data.get("response", {}).get("body", {})
    items = (body.get("items") or {}).get("item")
    if not items: return []
    if isinstance(items, dict): items = [items]
    if strict: items = [it for it in items if it.get("corpNm") == company_name]
    return items

def comma(n):
    try: return f"{int(str(n)):,}"
    except (ValueError, TypeError): return str(n) if n is not None else "-"

def fmt_date8(s: Optional[str]) -> str:
    if not s: return "-"
    s = str(s).strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else s

# ----------------------- 그래프/지표 유틸 -----------------------
def _to_int(x):
    try: return int(str(x))
    except Exception: return None

def _safe_ratio(num, den):
    if num is None or den in (None, 0): return None
    try: return round((num / den) * 100.0, 2)
    except Exception: return None

def _derive_quarter_key(basDt: Optional[str]):
    if not basDt: return None
    s = str(basDt).strip()
    if len(s) != 8 or (not s.isdigit()): return None
    y = int(s[:4]); m = int(s[4:6]); q = (m - 1) // 3 + 1
    if q < 1 or q > 4: return None
    return (y, q)

def _split_cfs_ofs(rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """연결/별도 관대한 분류 + fallback"""
    cfs, ofs, unknown = [], [], []
    for r in rows:
        code = (r.get("fnclDcd") or "").strip().upper()
        name = (r.get("fnclDcdNm") or "").strip()
        if code == "CFS" or ("연결" in name):
            cfs.append(r)
        elif code == "OFS" or ("별도" in name):
            ofs.append(r)
        else:
            unknown.append(r)
    if not cfs and not ofs:
        # 둘 다 비면 전체를 CFS로 취급
        cfs = unknown or rows[:]
        unknown = []
    else:
        # 남는 unknown은 존재하는 쪽에 합류 (우선 CFS)
        if unknown:
            (cfs if cfs else ofs).extend(unknown)
    return cfs, ofs

def _group_latest(rows: List[Dict], frequency: str = "annual") -> Dict[str, Dict]:
    grouped: Dict[str, Dict] = {}
    for r in rows:
        by = r.get("bizYear")
        bas = str(r.get("basDt") or "")
        by_str = str(by) if by is not None else ""
        if frequency == "annual":
            if not by_str.isdigit():
                # 연도가 없으면 basDt에서 유추
                k = _derive_quarter_key(bas)
                if not k: continue
                by_str = str(k[0])
            label = by_str
        else:
            k = _derive_quarter_key(bas)
            if not k: continue
            y, q = k
            label = f"{y}-Q{q}"
        if (label not in grouped) or (bas > str(grouped[label].get("basDt") or "")):
            grouped[label] = r
    return grouped

def _sorted_labels(labels: List[str], frequency: str) -> List[str]:
    if not labels: return []
    if frequency == "annual":
        return sorted(labels, key=lambda s: int(''.join(filter(str.isdigit, s)) or "0"))
    def key(lbl: str):
        try:
            y, q = lbl.split("-Q")
            return (int(y), int(q))
        except Exception:
            return (0, 0)
    return sorted(labels, key=key)

def _make_chart_data(rows: List[Dict], frequency: str = "annual") -> Dict:
    per = _group_latest(rows, frequency=frequency)
    labels = _sorted_labels(list(per.keys()), frequency=frequency)
    sales  = [_to_int(per[l].get("enpSaleAmt")) for l in labels]
    op     = [_to_int(per[l].get("enpBzopPft")) for l in labels]
    assets = [_to_int(per[l].get("enpTastAmt")) for l in labels]
    debt   = [_to_int(per[l].get("enpTdbtAmt")) for l in labels]
    equity = [_to_int(per[l].get("enpTcptAmt")) for l in labels]
    op_margin  = [_safe_ratio(op[i], sales[i]) for i in range(len(labels))]
    debt_ratio = [_safe_ratio(debt[i], equity[i]) for i in range(len(labels))]
    return {
        "labels": labels,
        "sales": sales,
        "op": op,
        "assets": assets,
        "debt": debt,
        "equity": equity,
        "op_margin": op_margin,
        "debt_ratio": debt_ratio,
    }

def build_chart_bundle(all_rows: List[Dict]) -> Dict:
    cfs, ofs = _split_cfs_ofs(all_rows or [])
    annual_cfs    = _make_chart_data(cfs, frequency="annual")     if cfs else {"labels": []}
    quarterly_cfs = _make_chart_data(cfs, frequency="quarterly")  if cfs else {"labels": []}
    annual_ofs    = _make_chart_data(ofs, frequency="annual")     if ofs else {"labels": []}
    quarterly_ofs = _make_chart_data(ofs, frequency="quarterly")  if ofs else {"labels": []}

    def has_data(d): return bool(d.get("labels"))

    has_cfs = has_data(annual_cfs) or has_data(quarterly_cfs)
    has_ofs = has_data(annual_ofs) or has_data(quarterly_ofs)
    default_consol = "CFS" if has_cfs else ("OFS" if has_ofs else "CFS")  # 최소 CFS 기본값

    return {
        "meta": {
            "has_cfs": has_cfs,
            "has_ofs": has_ofs,
            "has_any": has_cfs or has_ofs,
            "default_consol": default_consol,
            "default_frequency": "annual",
        },
        "annual":    {"CFS": annual_cfs,    "OFS": annual_ofs},
        "quarterly": {"CFS": quarterly_cfs, "OFS": quarterly_ofs},
    }
