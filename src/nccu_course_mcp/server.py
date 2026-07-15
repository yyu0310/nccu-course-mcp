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
    from client import search_raw, normalize, fetch_syllabus
except ImportError:
    from nccu_course_mcp.client import search_raw, normalize, fetch_syllabus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

mcp = FastMCP("NCCU Course MCP")

_DEPTS = json.loads((Path(__file__).parent / "dept_codes.json").read_text("utf-8"))["depts"]


def _level(code: str) -> str:
    """由三碼中間位推學制：0-4=大學部、5-8=研究所(碩博)、9xx=學程/在職專班。"""
    if code[0] == "9":
        return "學程/在職專班"
    return "大學部" if code[1] in "01234" else "研究所"


def _resolve_dept(dept: str) -> str:
    """把使用者給的『系名或代碼』解析成 dp3 代碼。同名跨學制時不猜，回錯誤請對方指定代碼。"""
    dept = dept.strip()
    if dept.isdigit() and len(dept) == 3:
        if dept not in _DEPTS:
            raise ValueError(f"代碼 {dept} 本學期無開課或不存在。用 list_departments 查有效代碼。")
        return dept
    hits = [c for c, v in _DEPTS.items() if dept in v["name"]]
    if not hits:
        raise ValueError(f"找不到系所「{dept}」。用 list_departments('{dept}') 查名稱。")
    if len(hits) > 1:
        opts = "、".join(f"{c}={_DEPTS[c]['name']}({_level(c)})" for c in hits)
        raise ValueError(f"「{dept}」對到多個系所/學制，請改用代碼：{opts}")
    return hits[0]


@mcp.tool()
def list_departments(query: str = "") -> list[dict]:
    """列出政大系所代碼表（snapshot）。傳 query 以官方系名子字串篩（如『財務』『法律』；用全名非簡稱）。

    回傳每筆: code(三碼)、name(中文系名)、level(大學部/研究所/學程)、course_count(snapshot 當時開課數)。
    code 首碼=學院、中間碼=學制(0大學部/5碩士)、可直接餵給 search_courses。
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

    回傳: {semester, dept_code, dept_name, count, courses:[...]}。
    每門課含 course_id/name/teacher/time/credits/kind/target/classroom/language/note/
    remain_url(即時餘額需另開)/syllabus_url。
    """
    code = _resolve_dept(dept)
    rows = [normalize(c) for c in search_raw(semester, code)]
    if keyword:
        k = keyword.lower()
        rows = [c for c in rows if k in c["name"].lower() or k in c["teacher"].lower() or k in c["note"].lower()]
    return {"semester": semester, "dept_code": code, "dept_name": _DEPTS[code]["name"],
            "count": len(rows), "courses": rows}


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
