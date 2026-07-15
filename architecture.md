# NCCU Course MCP — 架構

政大選課查詢（qrysub.nccu.edu.tw）的 MCP server，讓 AI／學生程式化查課。

## 設計原則

- **Live-only**：課程資料一律即時打政大 API，不存本地課程資料庫。
- **唯一靜態資產**：`dept_codes.json`（系所代碼↔中文系名 snapshot）。只是「系名翻譯字典」，不是課程快取。過期就重跑 `build_dept_codes.py` 重掃 live 更新。
- **YAGNI**：v0 不做資料庫、前端、排課引擎、餘額即時抓取（API 只給連結，未展開）。

## 逆向工程結論（Phase 0 實測，2026-07-15）

- 端點 → `GET https://es.nccu.edu.tw/course/zh-TW/:sem={學期}%20:dp3={系所碼}%20/`
- 完全公開 → 無 cookie / CSRF / session，任何人空手 GET 拿乾淨 JSON 陣列。
- 最小參數 → 只需 `sem` + `dp3`；`dp1`(院)/`dp2`(學制) 可省。dp3 是唯一系所鍵。
- **legacy TLS 坑** → 政大伺服器用舊版 TLS renegotiation，Python 預設 SSL 直接拒（`UNSAFE_LEGACY_RENEGOTIATION_DISABLED`）。client 掛 adapter 開 `OP_LEGACY_SERVER_CONNECT`(0x4) 才通。curl 無此問題。
- **500 筆硬上限** → 廣域查詢（省略 dp3、或只給 sem）伺服器最多回 500 筆會截斷。故一律逐系（帶 dp3）查詢，不做全校一次撈。

## 代碼制度

- 三碼制，全校共用：首碼=學院、中間碼=學制（0-4 大學部／5-8 研究所）、9xx=學程/在職專班。
- **dp3 = 課號前 3 碼 = 學號系所碼**，三者同源。例：財管 大學部 307、研究所 357。
- 同名跨學制會有兩碼（307/357 都叫「財務管理學系」），`_resolve_dept` 遇歧義不猜、回錯誤請對方指定代碼。

## 檔案結構

- `dept_codes.json` — 系所代碼 snapshot（115/07/15，83 系），server 載入用
- `requirements.txt` — mcp、requests
- `src/nccu_course_mcp/`
  - `client.py` — legacy-SSL session ＋ `search_raw()`（打 API）＋ `normalize()`（欄位正規化）
  - `server.py` — FastMCP，兩工具 `list_departments` / `search_courses`；`_resolve_dept`/`_level` 系名解析
  - `build_dept_codes.py` — 掃 live 重建 `dept_codes.json`（含系名字典種子）
  - `test_server.py` — 功能自測（實打 live）

## 工具

- `list_departments(query="")` → 系所表（code/name/level/course_count），query 以官方系名子字串篩。
- `search_courses(semester, dept, keyword="")` → 某系某學期開課；dept 收系名或三碼；keyword 篩課名/教師/備註。回傳正規化欄位（course_id/name/teacher/time/credits/kind/target/classroom/language/note/remain_url/syllabus_url）。
- `get_syllabus(syllabus_url)` → 讀教學大綱全文（純文字，含課程簡介/目標/學習成效/每週進度）。url 用 search_courses 的 `syllabus_url` 欄位（= API 的 `teaSchmUrl`，schmPrv 頁）。抓取限 nccu.edu.tw 網域。

> 註：course「更多」彈窗的欄位多數已在 search API 內（language/pay/core/far/tranTpe…），唯教學大綱需另抓 `teaSchmUrl`。餘額(`remain_url`)、選課設定(`subSetUrl`)、教師專長(`teaExpUrl`) 亦為另抓連結，暫未展開。

## 資料來源

- 課程 → es.nccu.edu.tw live API（見上）。
- 系名字典種子 → 政大教務處學系代號表 + qrysub 下拉選單（新設學程如 363 企研MBA、364 科智所補入）。「哪些代碼現行有效」以 live 是否回課為準。

## 待辦 / v2

- 系所簡稱別名（『財管』→財務管理學系），目前只認官方全名子字串。
- 即時餘額（打 `remain_url`）、跨系關鍵字全校搜、時間衝堂檢查、依選課準則自動篩選。
