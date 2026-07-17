"""NCCU Course MCP 功能自測（實打 live API）。跑: ../../.venv/bin/python test_server.py"""
import server as S

def run():
    # 1. 系名解析：代碼直給、唯一系名
    assert S._resolve_dept("357") == "357"
    assert S._resolve_dept("科技管理與智慧財產研究所") == "364"  # 唯一名
    # 2. 錯誤處理：不存在的代碼 / 系名
    for bad in ["999", "不存在系"]:
        try:
            S._resolve_dept(bad); assert False, f"{bad} 應報錯"
        except ValueError:
            pass
    # 3. 同名跨學制不猜：財務管理學系=307大學部/357研究所，須回錯誤且標學制
    try:
        S._resolve_dept("財務管理學系"); assert False, "同名應報歧義"
    except ValueError as e:
        assert "307" in str(e) and "357" in str(e) and "大學部" in str(e) and "研究所" in str(e)
    # level 來自 unit.json 單位樹（學士班→大學部、碩/博→研究所；921 在樹上掛社科院碩士班）
    assert S._level("307") == "大學部" and S._level("357") == "研究所" and S._level("921") == "研究所"
    # 4. search_courses 基本查詢
    r = S.search_courses("1151", "357")
    assert r["dept_code"] == "357" and r["dept_name"] == "財務管理學系"
    assert r["count"] == len(r["courses"]) > 0
    c0 = r["courses"][0]
    assert c0["course_id"] and c0["name"] and c0["teacher"], f"欄位缺: {c0}"
    # 5. keyword 篩選有效且為子集
    rk = S.search_courses("1151", "357", keyword="個案")
    assert rk["count"] <= r["count"]
    assert all("個案" in c["name"] or "個案" in c["teacher"] or "個案" in c["note"] for c in rk["courses"])
    # 6. list_departments 篩選
    fin = S.list_departments("財務")  # 官方全名子字串（簡稱『財管』留 v2 別名）
    assert any(d["code"] == "357" for d in fin)
    assert len(S.list_departments()) == 218

    # 6c. 全樹覆蓋抽查：體育、學分學程(P碼)、X實驗學院、創新國際學院
    for code, frag in [("6S1", "體育必修"), ("P53", "金融科技"), ("ZC0", "X實驗"), ("ZU1", "創新國際")]:
        assert frag in S._DEPTS[code]["name"], f"{code} 應收錄({frag})"

    # 6b. 整開/通識（全校共同課，課號 000 開頭、dp3=科目代碼）：2026-07-17 修的盲區
    assert S._resolve_dept("107") == "107" and S._level("107") == "整開"
    assert S._resolve_dept("2s1") == "2S1", "代碼字母應不分大小寫"
    econ = S.search_courses("1151", "107")
    assert econ["dept_name"] == "整開：經濟學" and econ["count"] >= 10
    assert all(c["course_id"].startswith("000") for c in econ["courses"]), "整開課號應為 000 開頭"
    try:  # 「經濟學」同時命中經濟學系與整開：經濟學 → 應報歧義並列出 107
        S._resolve_dept("經濟學"); assert False, "應報歧義"
    except ValueError as e:
        assert "107" in str(e) and "208" in str(e)

    # 6d. search_all 全校彈性查詢（2026-07-18 新增）
    ra = S.search_all("1151", keyword="賽局")
    assert any("賽局" in c["name"] for c in ra["courses"]) and not ra["truncated"]
    ra = S.search_all("1151", keyword="經濟學", week="3", language="中文")
    assert ra["count"] > 0 and all("三" in c["time"] for c in ra["courses"])
    ra = S.search_all("1151", teacher="郭炳伸")  # teacher 單獨用（自動兼作 keyword）
    assert any(c["course_id"] == "000219541" for c in ra["courses"]) and not ra["truncated"]

    # 6d-fix1: 無條件查詢應報錯（QA 發現的假象截斷坑）
    try:
        S.search_all("1151"); assert False, "無條件查詢應報錯"
    except ValueError:
        pass
    # 6d-fix2: 短英文關鍵字伺服器放水，matched 驗證要濾掉雜訊
    ai = S.search_all("1151", keyword="AI")
    assert all("ai" in c["name"].lower() or "ai" in c["teacher"].lower()
               or "ai" in c["note"].lower() or "AI" in c["course_id"] for c in ai["courses"]), \
        "AI 雜訊未濾乾淨"
    # 6d-fix3: 群組別名 '通識' 展開 + core_ge 不搭通識會警告
    ge = S.search_all("1151", dept="通識", core_ge="是", week="2")
    assert ge["count"] > 0 and all(c["core_ge"] == "是" for c in ge["courses"])
    bad = S.search_all("1151", keyword="統計學", core_ge="否")
    assert any("core_ge" in w for w in bad["warnings"]), "core_ge 濫用應警告"

    # 6e. check_schedule 衝堂檢查：note_facts 抽 TA 時間並併入檢查
    cs = S.check_schedule("1151", ["000359021", "000219541"])
    assert cs["ok"] and cs["courses"][0]["note_facts"]["ta_time"] == ["四7", "四8"]
    assert any("實習" in v for row in cs["timetable"].values() for v in row.values()), "TA 節次應標(實習)"
    cs = S.check_schedule("1151", ["000219541"], extra_times=["三234"])
    assert not cs["ok"] and cs["conflicts"][0]["overlap"] == ["三2", "三3", "三4"]
    try:
        S.check_schedule("1151", ["999999999"]); assert False, "壞課號應報錯"
    except ValueError:
        pass
    # slots 結構化欄位 + credits 數字化
    c = S.search_all("1151", keyword="000219111")["courses"][0]
    assert c["slots"] == ["三D", "三5", "三6"], f"slots 解析錯: {c['slots']}"
    assert c["credits"] == 3.0 and isinstance(c["credits"], float), "credits 應為數字"

    # 6f. note_facts.restriction：無「優先」二字的班級限定寫法也要抽到
    from client import mine_note
    assert "會一甲" in mine_note("會一甲，本課程為3學分，原則不接受加簽").get("restriction", "")
    assert mine_note("不接受加簽")["no_add"] is True

    # 7. 教學大綱：syllabus_url 指向 schmPrv(教學大綱)、抓得到全文且含課名
    eco = [c for c in r["courses"] if c["course_id"].startswith("357013")][0]
    assert "schmPrv" in eco["syllabus_url"], f"syllabus_url 應是教學大綱: {eco['syllabus_url']}"
    syl = S.get_syllabus(eco["syllabus_url"])
    assert "計量經濟學" in syl and "學習成效" in syl and len(syl) > 500, f"大綱內容異常({len(syl)}字)"
    # 8. host 白名單：非 nccu 網域須擋
    try:
        S.get_syllabus("https://evil.example.com/x.html"); assert False, "外部 URL 應被擋"
    except ValueError:
        pass

    print(f"✅ 全過。357 回 {r['count']} 門；『個案』篩後 {rk['count']} 門 = "
          + "、".join(c["name"] for c in rk["courses"])
          + f"；計量經濟學大綱 {len(syl)} 字可讀")

if __name__ == "__main__":
    run()
