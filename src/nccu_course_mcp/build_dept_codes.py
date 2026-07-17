"""重建系所代碼 snapshot：掃 live API 找出當前有開課的 dp3 代碼，配上中文系名。

系名字典種子來自政大教務處全校學系代號表（見 architecture.md 資料來源）；
「整開/通識/校級選修」的科目代碼另從 qrysub 的 unit.json 單位樹即時抓
（這批課號 000 開頭，dp3 是科目代碼如 107=經濟學，與課號前 3 碼脫鉤）。
代碼是否「現行有效」以 live API 是否回課為準——這就是「走線上路線」的更新方式：
改 SEM、重跑本檔，dept_codes.json 就更新到該學期。

用法: python build_dept_codes.py [學期]   例: python build_dept_codes.py 1151
"""
import json, re, sys, time
from pathlib import Path
try:  # 直跑或當 package import 都要能載
    from client import search_raw, _session  # 共用同一支 legacy-SSL client
except ImportError:
    from nccu_course_mcp.client import search_raw, _session

SEM = sys.argv[1] if len(sys.argv) > 1 else "1151"

# 系名字典（code -> 中文名）。政大三碼制：首碼=學院，全校共用。
# 種子來自教務處學系代號表 + qrysub 下拉選單（新設學程如 363/364 補於此）。
NAME = {
    # 文學院 1xx
    "101": "中國文學系", "102": "教育學系", "103": "歷史學系", "104": "哲學系",
    "109": "教育學程中心", "151": "中國文學系", "152": "教育學系", "153": "歷史學系",
    "154": "哲學系", "155": "圖書資訊與檔案學研究所", "156": "宗教研究所", "157": "幼兒教育研究所",
    # 社科/國關 2xx
    "202": "政治學系", "203": "外交學系", "204": "社會學系", "205": "財政學系",
    "206": "公共行政學系", "207": "地政學系", "208": "經濟學系", "209": "民族學系",
    "252": "政治學系", "253": "外交學系", "254": "社會學系", "255": "財政學系",
    "256": "公共行政學系", "257": "地政學系", "258": "經濟學系", "259": "民族學系",
    "260": "東亞研究所", "261": "中山人文社會科學研究所", "262": "勞工研究所", "263": "俄羅斯研究所",
    # 商學院 3xx（300=院級共同/不分系課）
    "300": "商學院不分系（院共同課）",
    "301": "國際貿易學系", "302": "金融學系", "303": "會計學系", "304": "統計學系",
    "305": "企業管理學系", "306": "資訊管理學系", "307": "財務管理學系", "308": "風險管理與保險學系",
    "351": "國際貿易學系", "352": "金融學系", "353": "會計學系", "354": "統計學系",
    "355": "企業管理學系", "356": "資訊管理學系", "357": "財務管理學系", "358": "風險管理與保險學系",
    "359": "科技管理研究所", "360": "經營管理碩士學程甲班", "361": "智慧財產研究所",
    "363": "企業管理研究所MBA學位學程", "364": "科技管理與智慧財產研究所",
    # 傳播學院 4xx
    "401": "新聞學系", "402": "廣告學系", "403": "廣播電視學系",
    "451": "新聞學系", "452": "廣告學系", "453": "廣播電視學系",
    # 外語學院 5xx
    "501": "英國語文學系", "502": "阿拉伯語文學系", "503": "東方語文學系", "504": "俄國語文學系",
    "506": "日本語文學系", "507": "韓國語文學系", "508": "土耳其語文學系",
    "551": "英國語文學系", "554": "俄國語文學系", "555": "語言學研究所", "556": "日本語文學系",
    # 法學院 6xx
    "601": "法律學系", "651": "法律學系",
    # 理學院 7xx
    "701": "應用數學系", "702": "心理學系", "703": "資訊科學系",
    "751": "應用數學系", "752": "心理學系", "753": "資訊科學系",
    # 學程/在職專班 9xx
    "911": "中等學校教師在職進修學校行政碩士學位班", "912": "中等學校教師在職進修國文教學碩士學位班",
    "921": "行政管理碩士學程", "922": "外交學系戰略與國際事務碩士在職專班", "923": "地政學系碩士在職專班",
    "924": "台灣研究碩士學程", "931": "經營管理碩士學程乙班", "932": "經營管理碩士學程",
    "933": "國際經營管理碩士學程", "934": "生物科技管理學程", "941": "新聞學系碩士在職專班",
    "951": "英國語文學系英語教學碩士在職專班", "961": "法律碩士在職進修專班",
    "981": "國家安全與大陸研究碩士在職專班",
}

# qrysub 前端的開課單位樹（靜態檔）＝查詢代碼的權威來源。
# L1=院級（含三個特殊單位：01 整開/通識/校級選修、02 輔系專班/學分學程專班、03 體育/國防），
# L2=學制或群組，L3=dp3 查詢代碼。注意：特殊單位的 dp3 是「科目/學程代碼」
# （107=經濟學、P01=學分學程、2S1=通識），與課號前 3 碼脫鉤（整開課號 000 開頭）。
UNIT_JSON = "https://qrysub.nccu.edu.tw/assets/api/unit.json"
SPECIAL_L1 = {"01", "02", "03"}  # 整開、輔系/學程專班、體育/國防
_zh = lambda s: re.sub(r"\s*/.*$", "", s).strip()  # 去掉英文尾綴


def fetch_units() -> dict:
    """掃整棵單位樹，回 {dp3: {"name":…, "level":…}}。同碼多掛（大學部+研究所）合併 level。"""
    tree = _session.get(UNIT_JSON, timeout=20).json()
    out = {}
    lv_map = {"學士班": "大學部", "碩士班": "研究所", "博士班": "研究所"}
    for l1 in tree:
        if l1["utCodL1"] == "0":
            continue
        for l2 in l1["utL2"]:
            if l2["utCodL2"] == "0":
                continue
            l2t = _zh(l2["utL2Text"])
            for l3 in l2["utL3"]:
                code, text = l3["utCodL3"].upper(), _zh(l3["utL3Text"])
                if code == "0":
                    continue
                if l1["utCodL1"] in SPECIAL_L1:
                    name, level = f"{l2t}：{text}", l2t
                else:
                    name, level = text, lv_map.get(l2t, l2t)
                if code in out:  # 同碼掛多學制/多學院：level 併集，名字保留首見
                    if level not in out[code]["level"]:
                        out[code]["level"] += f"/{level}"
                else:
                    out[code] = {"name": name, "level": level}
    return out


UNITS = fetch_units()
print(f"unit.json 單位樹共 {len(UNITS)} 個 dp3 代碼")

# 掃描候選：單位樹全部代碼 ∪ 系名字典（備援，防樹上暫時拿掉但仍有課的代碼）
candidates = sorted(set(UNITS) | set(NAME))

active = {}
for code in candidates:
    try:
        rows = search_raw(SEM, code)
    except Exception as e:
        print(f"  {code}: 錯誤 {e}")
        continue
    if rows:
        known = code in UNITS or code in NAME
        if code in UNITS:
            name = UNITS[code]["name"]
        else:
            name = NAME.get(code) or f"未知系所({rows[0].get('subGde','')[:6]})"
        active[code] = {"name": name, "course_count": len(rows), "named": known}
        if code in UNITS:
            active[code]["level"] = UNITS[code]["level"]
        flag = "" if known else "  ⚠ 字典缺名"
        print(f"  {code}: {len(rows):3d}門  {name}{flag}")
    time.sleep(0.12)

out = {"semester": SEM, "snapshot_date": "2026-07-15", "source": "es.nccu.edu.tw live API",
       "note": "code=課號前3碼=dp3；有課才收錄。更新: 改 SEM 重跑 build_dept_codes.py",
       "depts": dict(sorted(active.items()))}
p = Path(__file__).parent / "dept_codes.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n寫入 {p}  共 {len(active)} 系  未命名 {sum(1 for v in active.values() if not v['named'])} 個")
