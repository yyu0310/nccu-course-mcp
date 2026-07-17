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
from urllib.parse import quote

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


def query_raw(semester: str, keyword: str = "", dp3: str = "", week: str = "", lan: str = "") -> list[dict]:
    """組合查詢（逆向自 qrysub 前端 getData()）。所有條件是 AND。

    keyword: 自由文字，伺服器端搜課名/教師/備註/課號（課號全碼可精準反查單門課）。
    dp3: 開課單位代碼。week: '1'-'7'（週一~日）。lan: '1'=中文 '2'=英文。
    廣域查詢伺服器 500 筆截斷，呼叫端要檢查 len==500。
    """
    parts = [f":sem={semester}"]
    if keyword:
        k = keyword.replace("/", "／").replace("[", " ").replace("]", " ").strip()  # 前端 checkKeyword 同款清洗
        parts.append(k)
    if dp3:
        parts.append(f":dp3={dp3}")
    if week:
        parts.append(f":week={week}")
    if lan:
        parts.append(f":lan={lan}")
    url = BASE + "/" + quote(" ".join(parts) + " ") + "/"
    log.info("GET %s", url)
    r = _session.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    log.info("  <- %d 門課", len(data))
    if not isinstance(data, list):
        raise ValueError(f"預期陣列，收到 {type(data).__name__}: {str(data)[:120]}")
    return data


def search_raw(semester: str, dept_code: str) -> list[dict]:
    """打 API 拿某開課單位的原始課程陣列。semester 如 '1151'，dept_code 如 '357'。"""
    return query_raw(semester, dp3=dept_code)


# 政大節次時間表（實測推定：C=12:10 起、D=13:10 起、EFG=晚上）
PERIOD_TIME = {"1": "08:10", "2": "09:10", "3": "10:10", "4": "11:10", "C": "12:10",
               "D": "13:10", "5": "14:10", "6": "15:10", "7": "16:10", "8": "17:10",
               "E": "18:10", "F": "19:10", "G": "20:10", "A": "06:10", "B": "07:10"}


def parse_slots(sub_time: str) -> list[str]:
    """課表時間字串 → 節次清單。'三CD78' → ['三C','三D','三7','三8']；解不了回空清單。

    衝堂判斷用集合交集：set(a) & set(b) 非空即衝突。"""
    slots = []
    for day, periods in re.findall(r"([一二三四五六日])([0-9A-G]+)", sub_time or ""):
        slots += [day + p for p in periods]
    return slots


def mine_note(note: str) -> dict:
    """從備註自由文字抽結構化事實，弱模型不用自己讀中文備註。只回有命中的欄位。"""
    note = note or ""
    facts = {}
    m = re.search(r"實習課[為於]?[:：]?([一二三四五六日])[、,]?([0-9A-G]+)", note)
    if m:
        facts["ta_time"] = [m.group(1) + p for p in m.group(2)]
    m = re.search(r"(\d{2,3}\.\d{1,2}\.\d{1,2})[^。；]{0,12}?(?:舉行)?(會考|期末會考|期中考|期末考)", note)
    if m:
        facts["exam"] = f"{m.group(1)} {m.group(2)}"
    prio = re.findall(r"[^。；]*(?:優先|灌檔)[^。；]*", note)
    if prio:
        facts["priority"] = "；".join(p.strip() for p in prio)
    # 沒寫「優先」但實質限定的寫法：開頭班級代號（如「會一甲，…」）、限修句、專班字樣
    restr = []
    m = re.match(r"([一-鿿]{1,6}[一二三四][甲乙]?)[，,。]", note)
    if m:
        restr.append(m.group(1))
    restr += [s.strip() for s in re.findall(r"限[^。；，]{1,25}(?:修習|修讀|選課|學生|生)", note)]
    restr += [s.strip() for s in re.findall(r"[^。；，]{0,12}(?:專班|僑生|外國學生)[^。；，]{0,10}修讀", note)]
    if restr:
        facts["restriction"] = "；".join(dict.fromkeys(restr))
    if "不開放加簽" in note or "不得加簽" in note or "不接受加簽" in note:
        facts["no_add"] = True
    if "英語授課" in note or "英文授課" in note:
        facts["english_taught"] = True
    if "實習課" in note and "ta_time" not in facts:
        facts["has_ta_session"] = True  # 有實習課但備註沒寫時間，需查大綱或開學後公布
    return facts


# 欄位正規化：API 原欄位 -> 人話。只留常用，其餘丟 raw。
def normalize(c: dict) -> dict:
    note = (c.get("note") or "").replace("＠備註:", "").strip()
    out = {
        "course_id": c.get("subNum", ""),        # 課號(含班次尾碼)
        "name": c.get("subNam", ""),             # 課名
        "teacher": c.get("teaNam", ""),          # 授課教師
        "time": c.get("subTime", ""),            # 上課時間 例 二234
        "slots": parse_slots(c.get("subTime", "")),  # 結構化節次 ['二2','二3','二4']，衝堂判斷用
        "credits": float(c["subPoint"]) if str(c.get("subPoint", "")).replace(".", "", 1).isdigit() else c.get("subPoint", ""),  # 學分(數字)
        "kind": c.get("subKind", ""),            # 必修/選修
        "target": c.get("subGde", ""),           # 開課對象 例 財管碩一
        "classroom": c.get("subClassroom", ""),  # 教室
        "language": c.get("langTpe", ""),        # 授課語言
        "core_ge": c.get("core", ""),            # 核心通識標記 是/否（僅通識課有意義）
        "note": note,                            # 備註原文（值可能為 null）
        "remain_url": c.get("subRemainUrl", ""),  # 即時餘額(需另打此連結)
        "syllabus_url": c.get("teaSchmUrl", ""),  # 教學大綱(可餵 get_syllabus)
    }
    facts = mine_note(note)
    if facts:
        out["note_facts"] = facts  # 備註結構化：ta_time/exam/priority/no_add/english_taught
    return out


def fetch_syllabus(url: str) -> str:
    """抓教學大綱網頁並抽成純文字。限 nccu.edu.tw 網域（防被拿去打任意 URL）。"""
    if not re.match(r"^https://[\w.-]*\.nccu\.edu\.tw/", url):
        raise ValueError(f"只接受 nccu.edu.tw 網域的教學大綱連結，收到: {url[:80]}")
    if url.endswith("emptyforqry.htm"):
        return "（無大綱：這門課尚未上傳教學大綱，syllabus_url 是佔位頁）"
    log.info("GET syllabus %s", url)
    r = _session.get(url, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
    text = re.sub(r"(?s)<[^>]+>", " ", html).replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if "目前本系統沒有說明文件" in text or len(text) < 120:
        return "（無大綱：學校尚未上傳這門課的教學大綱，開學前後再查）"
    return text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rows = search_raw("1151", "357")
    assert rows, "財管碩(357) 不應為空"
    assert all("subNum" in c for c in rows), "缺 subNum 欄位"
    n = normalize(rows[0])
    assert n["course_id"] and n["name"] and n["teacher"], f"正規化欄位缺: {n}"
    print(f"OK: 357 回 {len(rows)} 門，首課 = {n['name']}｜{n['teacher']}｜{n['time']}")
