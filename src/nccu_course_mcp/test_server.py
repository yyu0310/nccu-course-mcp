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
    assert S._level("307") == "大學部" and S._level("357") == "研究所" and S._level("921") == "學程/在職專班"
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
    assert len(S.list_departments()) == 83

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
