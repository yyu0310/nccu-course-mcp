"""政大選課查詢 API client。

端點: GET https://es.nccu.edu.tw/course/zh-TW/:sem={學期}%20:dp3={系所碼}%20/
- 完全公開，無 cookie / token / session。
- 政大伺服器用舊版 TLS renegotiation，Python 預設 SSL 會拒（UNSAFE_LEGACY_RENEGOTIATION_DISABLED），
  故掛 legacy adapter 開 OP_LEGACY_SERVER_CONNECT。
- 只給 sem+dp3 即可，dp1/dp2 可省；dp3=系所碼(=課號前3碼)，回該系全學制的課。
- 廣域查詢（省略 dp3）伺服器上限 500 筆，故一律逐系查詢。
"""
import logging
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

log = logging.getLogger("nccu_course")
BASE = "https://es.nccu.edu.tw/course/zh-TW"
OP_LEGACY_SERVER_CONNECT = 0x4


class _LegacyTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **k):
        ctx = create_urllib3_context()
        ctx.options |= OP_LEGACY_SERVER_CONNECT
        k["ssl_context"] = ctx
        return super().init_poolmanager(*a, **k)


_session = requests.Session()
_session.mount("https://", _LegacyTLSAdapter())
_session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://qrysub.nccu.edu.tw",
    "Referer": "https://qrysub.nccu.edu.tw/",
})


def search_raw(semester: str, dept_code: str) -> list[dict]:
    """打 API 拿原始課程陣列。semester 如 '1151'，dept_code 如 '357'。"""
    url = f"{BASE}/:sem={semester}%20:dp3={dept_code}%20/"
    log.info("GET %s", url)
    r = _session.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    log.info("  <- %d 門課", len(data))
    if not isinstance(data, list):
        raise ValueError(f"預期陣列，收到 {type(data).__name__}: {str(data)[:120]}")
    return data


# 欄位正規化：API 原欄位 -> 人話。只留常用，其餘丟 raw。
def normalize(c: dict) -> dict:
    return {
        "course_id": c.get("subNum", ""),        # 課號(含班次尾碼)
        "name": c.get("subNam", ""),             # 課名
        "teacher": c.get("teaNam", ""),          # 授課教師
        "time": c.get("subTime", ""),            # 上課時間 例 二234
        "credits": c.get("subPoint", ""),        # 學分
        "kind": c.get("subKind", ""),            # 必修/選修
        "target": c.get("subGde", ""),           # 開課對象 例 財管碩一
        "classroom": c.get("subClassroom", ""),  # 教室
        "language": c.get("langTpe", ""),        # 授課語言
        "note": (c.get("note") or "").replace("＠備註:", "").strip(),  # 備註（值可能為 null）
        "remain_url": c.get("subRemainUrl", ""),  # 即時餘額(需另打此連結)
        "syllabus_url": c.get("teaSchmUrl", ""),  # 教學大綱(可餵 get_syllabus)
    }


def fetch_syllabus(url: str) -> str:
    """抓教學大綱網頁並抽成純文字。限 nccu.edu.tw 網域（防被拿去打任意 URL）。"""
    if not re.match(r"^https://[\w.-]*\.nccu\.edu\.tw/", url):
        raise ValueError(f"只接受 nccu.edu.tw 網域的教學大綱連結，收到: {url[:80]}")
    log.info("GET syllabus %s", url)
    r = _session.get(url, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
    text = re.sub(r"(?s)<[^>]+>", " ", html).replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rows = search_raw("1151", "357")
    assert rows, "財管碩(357) 不應為空"
    assert all("subNum" in c for c in rows), "缺 subNum 欄位"
    n = normalize(rows[0])
    assert n["course_id"] and n["name"] and n["teacher"], f"正規化欄位缺: {n}"
    print(f"OK: 357 回 {len(rows)} 門，首課 = {n['name']}｜{n['teacher']}｜{n['time']}")
