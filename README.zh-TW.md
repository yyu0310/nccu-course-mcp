# NCCU Course MCP

政大選課查詢（qrysub.nccu.edu.tw）的 MCP server，讓 AI Agent 或學生用自然語言查課，
不用再跟難用的網頁介面搏鬥。

**不知道從哪開始？** 把這頁的網址貼給你的 AI Coding Agent（如 Claude Code、Codex
等），說「幫我安裝這個 MCP server」，它自己就能跑完下面幾乎所有步驟，只有一個密碼
相關的步驟要你自己動手。

課程資料每次查詢都**即時**打政大公開課程 API，不存本地課程資料庫。唯一附帶的資料檔是
`dept_codes.json`（系所代碼對中文系名的 snapshot，隨時可用 `build_dept_codes.py` 重新產生）。

## 工具

- `search_all(semester, keyword="", week="", language="", dept="", kind="", core_ge="", teacher="")`：
  全校跨單位彈性查課。關鍵字由伺服器端搜課名／教師／備註／完整課號，可再用星期、
  授課語言、必選修、核心通識、教師名過濾。不知道課掛在哪個單位時用這個。
- `check_schedule(semester, course_ids, extra_times=[])`：衝堂檢查。給完整課號清單，
  回衝突明細＋週課表；備註裡的 TA 實習課時間會自動併入檢查。
- `list_departments(query="")`：列出開課單位代碼（含系所、整開科目、通識、體育、
  學分學程），可用名稱子字串篩選。
- `search_courses(semester, dept, keyword="")`：查某開課單位某學期的開課。
  - `semester`：學年+學期，例如 `1151` = 115 學年第 1 學期。
  - `dept`：單位名或代碼（例如 `財務管理學系`、`357`、`107`＝整開的經濟學）。
- `get_syllabus(syllabus_url)`：讀取某門課的教學大綱全文（課程簡介、課程目標、學習成效、
  每週進度）。僅接受 nccu.edu.tw 網域的連結。
- `get_course_rating(semester, course_id="", teacher="", course_name="")`：
  某位教師近六學期的教學意見調查評量（依政大規定僅開放近六學期），含分數與每學期
  學生填寫的文字意見。**選用功能，需要你自己的政大帳密**，見下方說明；其餘工具一律
  匿名，不需登入。

每門課都回結構化欄位：`slots`（節次清單，衝堂判斷不用解析「三CD78」）、`note_facts`
（備註抽取：實習課時間／會考日期／優先系／加簽限制／英語授課）、`syllabus_url`。
查詢配方與選課領域知識見 [QUERY_GUIDE.md](QUERY_GUIDE.md)。

## 安裝

> **AI Agent 在幫忙裝這個？** 這節的指令直接自己跑，不用先問人類。跑到下面「選用
> 功能」那節之前先停下來讀一遍說明，裡面有一步絕對不能代替人類做。

### 推薦：免 clone、免建 venv（需要 [uv](https://docs.astral.sh/uv/)）

直接從 GitHub 跑，給 Claude Code：

```bash
claude mcp add nccu-course -- uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp
```

沒有 `uv`？裝一次即可：`curl -LsSf https://astral.sh/uv/install.sh | sh`

### 無 uv 備援：只用 pip

任何 Python 3.10+ 皆可（用 `pipx` 保持隔離）：

```bash
pipx install git+https://github.com/yyu0310/nccu-course-mcp
claude mcp add nccu-course -- nccu-course-mcp
```

或加進任何 MCP 客戶端的設定檔（例如 Claude Desktop 的 `claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "nccu-course": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/yyu0310/nccu-course-mcp", "nccu-course-mcp"]
    }
  }
}
```

### 從原始碼

```bash
git clone https://github.com/yyu0310/nccu-course-mcp && cd nccu-course-mcp
python -m venv .venv && ./.venv/bin/pip install -e .
./.venv/bin/python src/nccu_course_mcp/test_server.py   # 實打 live 自測
claude mcp add nccu-course -- ./.venv/bin/nccu-course-mcp
```

## 選用功能：自動化查課程評價（`get_course_rating`）

其餘工具一律匿名，不需任何設定。`get_course_rating` 是唯一例外：政大只對登入學生
開放教師評量歷史，所以這支工具需要你自己的政大帳密。不需要這支工具就跳過整節，
不影響其他工具運作。

### 第一步（你自己做，不要讓 AI Agent 代勞）

把政大入口網密碼存進電腦的憑證儲存區，只做一次。**如果是 AI Agent 在幫你裝這個，
不要讓它跑這條指令、也不要讓它幫你輸入密碼**，自己開一個終端機親手跑：

```bash
python3 -c "import keyring; keyring.set_password('nccu-ldap', '<你的學號>', input())"
```

它會問你密碼，輸入時畫面不顯示字元。這用的是 `keyring` 這個套件，macOS
（Keychain）、Windows（認證管理員）、Linux（Secret Service）都是同一條指令。密碼
永不落地明文、不進 log，不管是這支工具還是幫你裝機的 AI Agent 都看不到。

### 第二步（AI Agent 可以幫你做）

跟它說你的學號（不是機密，只是要知道追蹤清單掛在誰名下），讓它在跑這個 server 的
地方設定 `NCCU_STUDENT_ID`，例如 MCP 客戶端設定檔：

```json
{
  "mcpServers": {
    "nccu-course": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/yyu0310/nccu-course-mcp", "nccu-course-mcp"],
      "env": { "NCCU_STUDENT_ID": "<你的學號>" }
    }
  }
}
```

## 說明

- 上游伺服器使用舊版 TLS renegotiation，client 開啟 `OP_LEGACY_SERVER_CONNECT` 才連得上。
- 廣域查詢上游有 500 筆上限，因此一律逐系查詢。
- 只用政大公開的課程目錄，不需登入，唯一例外是上方選用的 `get_course_rating`。
