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

- 查詢代碼的權威來源是 qrysub 前端靜態檔 `https://qrysub.nccu.edu.tw/assets/api/unit.json`（單位樹：L1=院級 17 個、L2=學制/群組、L3=dp3 代碼）。`build_dept_codes.py` 掃整棵樹＋live 驗證有課才收錄；手維 NAME 字典僅備援。
- 一般系所：三碼數字，首碼=學院、**dp3 = 課號前 3 碼 = 系所碼**。例：財管 大學部 307、研究所 357。
- **例外（2026-07-17 修的盲區）：dp3 ≠ 課號前 3 碼的三個特殊 L1**——
  - 整開/通識/校級選修（L1=01）：dp3 是科目代碼（107=經濟學、113=初級會計學、2S4=社會科學類通識），課號卻是 000 開頭。全校/全院共同課（大一經濟學 16 班等）全掛這裡。
  - 輔系專班/學分學程專班（L1=02）：3S1-3S8 輔系、P01-P79 學分學程。
  - 體育/全民國防（L1=03）：6S1 體育必修、6S2 體育選修、6S3 適應體育、7S1 全民國防。
  - 另有字母代碼學院：ZU1/ZM1 創新國際、ZC0 X實驗學院、NU1 運動產業學程、1T3 師培中心、5T1 外文中心。
- 學制（level）以單位樹 L2 為準（學士班→大學部、碩/博→研究所、同碼多掛併集如「大學部/研究所」），特殊單位存群組名（整開/通識/體育課程…）。
- 同名跨學制/跨單位會有多碼（307/357 都叫「財務管理學系」；「經濟學」命中經濟學系 208 與整開 107），`_resolve_dept` 遇歧義不猜、回錯誤請對方指定代碼。

## 檔案結構

- `pyproject.toml`：套件與依賴（`mcp>=1.2.0,<2`、`requests`、`beautifulsoup4`、`keyring`），入口指令 `nccu-course-mcp`；`mcp<2` 的原因見 AGENTS.md Gotchas
- `src/nccu_course_mcp/`
  - `client.py` — legacy-SSL session ＋ `search_raw()`（打 API）＋ `normalize()`（欄位正規化）
  - `dept_codes.json`：開課單位代碼 snapshot（2026-07-17 全樹重掃，218 個代碼），server 載入用
  - `server.py`：FastMCP 入口，六個工具 `search_all` / `check_schedule` / `list_departments` / `search_courses` / `get_syllabus` / `get_course_rating`；`_resolve_dept`/`_level` 系名解析
  - `rate.py`：登入、追蹤清單、評價頁與文字意見解析，只供 `get_course_rating` 使用（資料流見下方「評量工具資料流」）
  - `build_dept_codes.py` — 掃 live 重建 `dept_codes.json`（含系名字典種子）
  - `test_server.py` — 功能自測（實打 live）

## 工具（v2，2026-07-18 高彈性改版）

- `search_all(semester, keyword, week, language, dept, kind, core_ge, teacher)` → 全校跨單位彈性查詢。keyword 伺服器端搜課名/教師/備註/完整課號（課號全碼＝精準反查）；week=1-7、language 中文/英文 伺服器端過濾；kind/core_ge/teacher 本地過濾。回 truncated 旗標（命中 500 上限）。
- `check_schedule(semester, course_ids, extra_times)` → 決定性衝堂檢查：課號用 keyword 反查、slots 交集、note_facts.ta_time 自動併入、回衝突明細＋週課表。
- `list_departments(query="")` → 開課單位表（code/name/level/course_count）。
- `search_courses(semester, dept, keyword="")` → 某單位某學期開課。
- `get_syllabus(syllabus_url)` → 讀教學大綱全文。抓取限 nccu.edu.tw 網域。

正規化欄位新增：`slots`（parse_slots 解「三CD78」→ ['三C','三D','三7','三8']）、`core_ge`（核心通識 是/否）、`note_facts`（mine_note 抽備註：ta_time/exam/priority/no_add/english_taught/has_ta_session）。

### 縮小強弱模型差距的設計（2026-07-18）

原則：模型會做錯的事下沉成工具保證——時間解析（slots）、備註暗雷（note_facts）、衝堂判斷（check_schedule）、截斷警示（truncated）全部決定性計算；查詢指南寫進 docstring（所有 MCP client 都看得到）；QUERY_GUIDE.md 是給人與讀 repo 的 agent 的鏡像文件。

### 查詢文法（逆向 qrysub main JS 的 getData()，2026-07-18）

- 關鍵字直接放路徑（無參數名），伺服器端全文搜；`/`→`／`、`[]`→空白（checkKeyword 同款清洗）。
- `:week=1-7`、`:lan=1中文/2英文`、`:dp1/:dp2/:dp3` 可自由組合，全 AND。
- `:curn=`（前端的課號查詢參數）實測各種格式都回 0，棄用；課號當 keyword 反而精準命中。
- 單位樹靜態檔 `qrysub.nccu.edu.tw/assets/api/unit.json`＝dp1/dp2/dp3 權威來源。

> 註：course「更多」彈窗的欄位多數已在 search API 內（language/pay/core/far/tranTpe…），唯教學大綱需另抓 `teaSchmUrl`。餘額(`remain_url`)、選課設定(`subSetUrl`)、教師專長(`teaExpUrl`) 亦為另抓連結，暫未展開。

## 評量工具資料流（`get_course_rating` / `rate.py`，2026-09-20 補）

唯一需要登入的工具。為什麼要登入：教學評價頁的網址（`teaStatUrl`，內含教師代號 tnum）只出現在登入後的「追蹤清單」回傳裡，查不到公開來源；評價頁本身免登入。

流程（`server.get_course_rating` 依序呼叫 `rate.py`）：

1. 取憑證：學號讀環境變數 `NCCU_STUDENT_ID`，密碼從系統 keyring 讀（service `nccu-ldap`），兩者都不落地、log 一律遮罩。
2. `login`：POST `es.nccu.edu.tw/person/{編碼後的 學號!!)密碼}/` → 回傳 `encstu`（登入 token）。`/`、`\` 先換成全形，模擬前端 checkLdapParam，這不是加密。失敗時 `encstu=ERROR`。
3. `resolve_tea_stat_url`：
   - 加入追蹤：POST `tracing/C/{lang}/1{課號}-{encstu}/`
   - 讀追蹤清單：POST `tracing/{lang}/{encstu}/`，**不可帶學期段**（帶了會回同筆數但欄位全 null，見 AGENTS.md Gotchas），找到該課那筆的 `teaStatUrl`
   - 移出追蹤：POST `tracing/D/{lang}/{課號}-{encstu}/`，放在 `finally`，避免弄髒使用者真實的追蹤清單（清理失敗只 warning、不中斷）
   - 該課沒有評價紀錄（例如教師第一次開這門課）時回 None，工具回報查無資料
4. `fetch_rating`：`teaStatUrl` 指向 `statisticAll.jsp`（只是 frameset 外殼），字串替換成 `statistic.jsp` 再 GET（免登入），`_parse_statistic` 解 9 欄評價表。
5. `fetch_comments`：每列若有文字意見連結（相對路徑，先 urljoin 成完整網址）再 GET 一次，取回學生意見；`with_comments=False` 可跳過、只回分數。

信任邊界：`fetch_rating` 只接受 `*.nccu.edu.tw` 網址。

## 資料來源

- 課程 → es.nccu.edu.tw live API（見上）。
- 系名字典種子 → 政大教務處學系代號表 + qrysub 下拉選單（新設學程如 363 企研MBA、364 科智所補入）。「哪些代碼現行有效」以 live 是否回課為準。

## 待辦 / v2

- 系所簡稱別名（『財管』→財務管理學系），目前只認官方全名子字串。
- 即時餘額（打 `remain_url`）、跨系關鍵字全校搜、時間衝堂檢查、依選課準則自動篩選。
