"""NCCU Course MCP — 政大選課查詢 MCP server。

Live-only：課程一律即時打 es.nccu.edu.tw，不存本地課程 DB。
唯一靜態資產 dept_codes.json（系所代碼↔中文名 snapshot），供系名解析用；
過期就重跑 build_dept_codes.py 重掃。

工具:
  list_departments(query?)          列系所代碼表，可用關鍵字篩
  search_courses(semester, dept, keyword?)  查某系某學期開課
"""
import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP
try:  # 直跑 server.py 或當 package import 都要能載
    from client import search_raw, query_raw, normalize, fetch_syllabus, parse_slots
except ImportError:
    from nccu_course_mcp.client import search_raw, query_raw, normalize, fetch_syllabus, parse_slots

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

mcp = FastMCP("NCCU Course MCP")

_DEPTS = json.loads((Path(__file__).parent / "dept_codes.json").read_text("utf-8"))["depts"]


def _level(code: str) -> str:
    """學制：整開/通識/校級選修由 snapshot 的 level 欄位標示（其 dp3 是科目代碼非系所碼）；
    其餘由三碼中間位推：0-4=大學部、5-8=研究所(碩博)、9xx=學程/在職專班。"""
    stored = _DEPTS.get(code, {}).get("level")
    if stored:
        return stored
    if code[0] == "9":
        return "學程/在職專班"
    return "大學部" if code[1] in "01234" else "研究所"


# 群組別名：一個詞展開成多個 dp3 代碼一次查完（通識 8 類不用手動迴圈）
_GROUP_ALIAS = {"通識": "通識", "整開": "整開", "體育": "體育課程", "學分學程": "學分學程專班", "輔系": "輔系專班"}


def _expand_group(dept: str) -> list[str]:
    """『通識』『整開』『體育』等群組詞 → 該群組全部代碼；不是群組詞回空清單。"""
    level = _GROUP_ALIAS.get(dept.strip())
    if not level:
        return []
    return [c for c, v in _DEPTS.items() if v.get("level", "").startswith(level)]


def _resolve_dept(dept: str) -> str:
    """把使用者給的『系名或代碼』解析成 dp3 代碼。同名跨學制時不猜，回錯誤請對方指定代碼。"""
    dept = dept.strip()
    if len(dept) == 3 and dept.isascii():  # 代碼可含字母：通識 2S1、校級選修 9S1
        code = dept.upper()
        if code not in _DEPTS:
            raise ValueError(f"代碼 {code} 本學期無開課或不存在。用 list_departments 查有效代碼。")
        return code
    hits = [c for c, v in _DEPTS.items() if dept in v["name"]]
    if not hits:
        # 模糊備援：拿輸入的 2 字滑窗找相近系名（「企研所」→ 企業管理研究所MBA…）
        grams = {dept[i:i + 2] for i in range(len(dept) - 1)}
        near = [c for c, v in _DEPTS.items() if any(g in v["name"] for g in grams)]
        hint = "；相近的有：" + "、".join(f"{c}={_DEPTS[c]['name']}" for c in near[:5]) if near else ""
        raise ValueError(f"找不到系所「{dept}」。用 list_departments('{dept}') 查名稱{hint}")
    if len(hits) > 1:
        opts = "、".join(f"{c}={_DEPTS[c]['name']}({_level(c)})" for c in hits)
        raise ValueError(f"「{dept}」對到多個系所/學制，請改用代碼：{opts}")
    return hits[0]


@mcp.tool()
def list_departments(query: str = "") -> list[dict]:
    """列出政大開課單位代碼表（snapshot）。傳 query 以名稱子字串篩（如『財務』『通識』；用全名非簡稱）。

    ★選課常識（先看）: 大一大二全校共同必修（經濟學/統計學/初級會計學/微積分/大學英文…）
    不掛在各系代碼下，而掛在「整開」科目代碼（課號 000 開頭）；通識掛 2S1-2S8、體育必修
    6S1、適應體育 6S3、輔系專班 3S1-3S8、學分學程 P01-P79。查系代碼找不到某門課時，
    十之八九是它其實掛在這些共同單位下——改用 search_all(keyword=課名) 全校搜最快。

    回傳型別是 list[dict]（不是包在物件裡）。每筆: code(三碼，可含字母如 2S4/P53/ZU1)、
    name(中文名)、level(大學部/研究所/學程/整開/通識/校級選修/體育課程…)、course_count。
    code 可直接餵給 search_courses 或 search_all(dept=...)；群組詞（'通識'/'整開'/'體育'/
    '學分學程'/'輔系'）可直接餵給 search_all(dept=...) 一次查完整組。
    """
    items = [{"code": c, "name": v["name"], "level": _level(c), "course_count": v["course_count"]}
             for c, v in _DEPTS.items() if not query or query in v["name"]]
    return items


@mcp.tool()
def search_courses(semester: str, dept: str, keyword: str = "") -> dict:
    """查某系所某學期的開課清單（即時查政大 API）。

    參數:
      semester: 學期碼，格式『學年+學期』，如 1151 = 115學年第1學期、1142 = 114學年第2學期。
      dept:     系所中文名或三碼代碼，如『財務管理學系』或『357』。用 list_departments 查代碼。
      keyword:  選填。以關鍵字篩課名/教師/備註（如『交易』『個案』）。

    回傳: {semester, dept_code, dept_name, count, courses:[...]}。每門課欄位同 search_all
    （course_id/name/teacher/time/slots/credits(數字)/kind/target/classroom/language/
    core_ge/note/note_facts/remain_url/syllabus_url），note_facts 見 search_all 說明。
    要跨單位搜、或不確定課掛哪個單位，用 search_all；本工具限單一單位。
    """
    code = _resolve_dept(dept)
    rows = [normalize(c) for c in search_raw(semester, code)]
    if keyword:
        k = keyword.lower()
        rows = [c for c in rows if k in c["name"].lower() or k in c["teacher"].lower() or k in c["note"].lower()]
    return {"semester": semester, "dept_code": code, "dept_name": _DEPTS[code]["name"],
            "count": len(rows), "courses": rows}


PERIOD_TABLE = ("節次對照: 1=08:10 2=09:10 3=10:10 4=11:10 C=12:10 D=13:10 5=14:10 "
                "6=15:10 7=16:10 8=17:10 E=18:10 F=19:10 G=20:10（各 50 分鐘）")


@mcp.tool()
def search_all(semester: str, keyword: str = "", week: str = "", language: str = "",
               dept: str = "", kind: str = "", core_ge: str = "", teacher: str = "") -> dict:
    """全校跨單位彈性查課（伺服器端關鍵字搜尋，意圖查詢的主力工具）。

    典型用法（條件全部 AND）:
      search_all("1151", keyword="賽局")            → 全校課名/教師/備註含「賽局」的課
      search_all("1151", keyword="經濟學", week="3", language="中文") → 週三的中文經濟學課
      search_all("1151", keyword="000219541")       → 用完整 9 碼課號精準反查單門課
      search_all("1151", teacher="郭力昕")          → 這位老師全校開的所有課
      search_all("1151", dept="通識", core_ge="是", week="2") → 週二的核心通識（8 類一次查）

    參數:
      semester: 學期碼，如 1151 = 115學年第1學期。
      keyword:  自由文字。伺服器端搜課名、教師名、備註、完整課號。
                注意會命中「備註提到」的課（如備註寫先修經濟學），看 matched 欄位分辨。
      week:     '1'-'7'（週一~週日），伺服器端過濾。
      language: '中文' 或 '英文'，伺服器端過濾。
      dept:     開課單位（代碼或中文名），或群組詞：'通識'(2S1-2S8)/'整開'/'體育'/
                '學分學程'/'輔系'，群組詞會自動展開成多個代碼一次查完。
      kind:     '必修'/'選修'/'群修'，本地過濾（整開課此欄常為空，過濾會漏，慎用）。
      core_ge:  '是'=核心通識、'否'=一般通識。務必搭配 dept='通識'（或 2S1-2S8）使用：
                非通識課的此欄位也是'否'，不限單位會混入全校非通識課。
      teacher:  教師名（含合開課），會自動兼作伺服器端關鍵字，可單獨使用。

    keyword 與 dept 至少給一個（teacher 也算 keyword），否則報錯——無條件廣域查詢會被
    伺服器 500 筆截斷，得到的是不完整的假象。

    回傳 {count, truncated, warnings, courses:[...]}。truncated=True 表示伺服器端撈取命中
    500 筆上限，本地過濾後的結果「不完整」，請加條件縮小再查。
    每門課的欄位: course_id/name/teacher/time/slots(結構化節次)/credits(數字)/kind/target/
    classroom/language/core_ge/note/note_facts/matched/remain_url/syllabus_url。
    - matched: 這筆命中關鍵字的欄位（name/teacher/note/course_id），過濾雜訊用。
    - note_facts 只在備註有料時出現，用 .get('note_facts', {}) 存取。內含:
      ta_time(實習課節次)/exam(會考日)/priority(優先/灌檔系所)/restriction(限修班級)/
      no_add(不可加簽)/english_taught/has_ta_session(有實習課但時間未定)。
    - target 是「開課對象」非選課資格；真正的資格限制看 note_facts.restriction/priority。
    - """ + PERIOD_TABLE + """

    選課常識（重要）: 大一大二全校共同必修（經濟學/統計學/初級會計學/微積分/大學英文…）
    不在各系代碼下，掛在「整開」科目代碼（dept='整開' 一次查、或 list_departments('整開')）；
    通識掛 2S1-2S8（dept='通識'）；體育必修 6S1、適應體育 6S3；輔系專班 3S1-3S8。
    查不到課時先懷疑單位掛錯，改用 keyword 全校搜。
    """
    if not keyword and not dept and not teacher:
        raise ValueError("keyword、dept、teacher 至少給一個。無條件廣域查詢會被伺服器截斷在 "
                         "500 筆，結果不可信。想看某單位全部課請用 dept 或 search_courses。")
    kw = keyword or teacher  # 只給 teacher 時自動兼作伺服器端關鍵字，避免撞 500 上限
    lan = {"中文": "1", "英文": "2", "1": "1", "2": "2"}.get(language.strip(), "") if language else ""
    group = _expand_group(dept) if dept else []
    dp3_list = group or ([_resolve_dept(dept)] if dept else [""])

    raw, truncated = [], False
    seen = set()
    for dp3 in dp3_list:
        rows = query_raw(semester, keyword=kw, dp3=dp3, week=week, lan=lan)
        truncated = truncated or len(rows) == 500
        for r in rows:
            if r.get("subNum") not in seen:  # 通識同課跨類別重複掛，去重
                seen.add(r.get("subNum"))
                raw.append(r)

    courses, warnings = [], []
    for c in map(normalize, raw):
        if kw:  # 本地驗證關鍵字真的出現在哪個欄位；伺服器對短英文字會放水（如 'AI'）
            m = ("course_id" if kw in c["course_id"] else "name" if kw.lower() in c["name"].lower()
                 else "teacher" if kw in c["teacher"] else "note" if kw.lower() in c["note"].lower() else "")
            c["matched"] = m
            if not m and truncated:
                continue  # 撈取已截斷且驗證不到關鍵字 → 伺服器放水的雜訊，丟掉
        courses.append(c)
    if kind:
        courses = [c for c in courses if kind in c["kind"]]
    if core_ge:
        courses = [c for c in courses if c["core_ge"] == core_ge]
        if not group and not (dept and dept.upper().startswith("2S")):
            warnings.append("core_ge 只對通識課有意義，目前查詢範圍不限於通識，"
                            "結果可能混入非通識課，建議 dept='通識' 再查一次。")
    if teacher:
        courses = [c for c in courses if teacher in c["teacher"]]
    if truncated:
        warnings.append("伺服器端撈取命中 500 筆上限，結果不完整，請加 week/language/dept 縮小。")
    return {"semester": semester, "count": len(courses), "truncated": truncated,
            "warnings": warnings, "courses": courses}


@mcp.tool()
def check_schedule(semester: str, course_ids: list[str], extra_times: list[str] = []) -> dict:
    """衝堂檢查（決定性計算，不用自己解析時間字串）。排課表的最後一步必用。

    參數:
      semester:    學期碼，如 1151。
      course_ids:  完整「9 碼」課號清單，如 ["000219541", "000359021"]（6 碼查不到會報錯）。
      extra_times: 額外時段字串，如 TA 實習課 ["四78"]、打工時段 ["五EFG"]。

    回傳（dict）:
      ok:        True=完全不衝堂。注意：時間未定的課不在判斷範圍（見 warnings）。
      conflicts: 衝突清單 [{a, b, overlap:[節次], cross_listed?}]。cross_listed=True 表示
                 兩門課同教師同教室同時段，多半是學碩合開同一堂課，不是真衝堂。
      warnings:  ["某課時間未定或無法解析，未納入衝堂判斷", ...]。
      timetable: {週幾: {節次: 課名}} 週課表；TA 實習課節次標 "(實習)"。
      courses:   list（依 course_ids 順序），每項是該課的正規化資料（含 slots 與
                 note_facts；note_facts.ta_time 有值時已自動併入該課時段一起檢查）。
    """ + PERIOD_TABLE
    items, warnings = [], []
    for cid in course_ids:
        rows = query_raw(semester, keyword=cid)
        hit = [r for r in rows if r.get("subNum") == cid]
        if not hit:
            raise ValueError(f"課號 {cid} 在 {semester} 查無此課（要 9 碼完整課號，"
                             f"可先用 search_all(keyword=課名) 查到 course_id 再來）")
        c = normalize(hit[0])
        slots = list(c["slots"])
        ta = (c.get("note_facts") or {}).get("ta_time") or []
        label = f"{c['name']}({c['teacher']})"
        if not slots:
            warnings.append(f"{label} 時間「{c['time'] or '未定'}」無法解析，未納入衝堂判斷")
        items.append({"label": label, "slots": slots + ta, "ta": set(ta), "course": c})
    for i, t in enumerate(extra_times):
        items.append({"label": f"額外時段{i+1}:{t}", "slots": parse_slots(t), "ta": set(), "course": None})

    conflicts = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            ov = sorted(set(a["slots"]) & set(b["slots"]))
            if not ov:
                continue
            conf = {"a": a["label"], "b": b["label"], "overlap": ov}
            ca, cb = a["course"], b["course"]
            if ca and cb and ca["teacher"] == cb["teacher"] and ca["classroom"] == cb["classroom"] \
                    and set(ca["slots"]) == set(cb["slots"]):
                conf["cross_listed"] = True  # 學碩合開同堂課，非真衝堂
            conflicts.append(conf)
    timetable = {}
    for it in items:
        for s in it["slots"]:
            day, period = s[0], s[1:]
            tag = "(實習)" if s in it["ta"] else ""
            timetable.setdefault(day, {})[period] = it["label"] + tag
    real = [c for c in conflicts if not c.get("cross_listed")]
    return {"ok": not real, "conflicts": conflicts, "warnings": warnings, "timetable": timetable,
            "courses": [it["course"] for it in items if it["course"]]}


@mcp.tool()
def get_syllabus(syllabus_url: str) -> str:
    """讀取一門課的教學大綱全文（純文字）。

    syllabus_url 用 search_courses 回傳的 syllabus_url 欄位。
    內容含課程簡介、課程目標與學習成效、每週進度、評分方式等，可據以判斷課程性質。
    """
    return fetch_syllabus(syllabus_url)


def main():
    """console_script 進入點（pyproject 的 nccu-course-mcp 指到這）。"""
    mcp.run()


if __name__ == "__main__":
    main()
