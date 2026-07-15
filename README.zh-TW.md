# NCCU Course MCP

政大選課查詢（qrysub.nccu.edu.tw）的 MCP server，讓 AI 助理或學生用自然語言查課，
不用再跟難用的網頁介面搏鬥。

課程資料每次查詢都**即時**打政大公開課程 API，不存本地課程資料庫。唯一附帶的資料檔是
`dept_codes.json`（系所代碼對中文系名的 snapshot，隨時可用 `build_dept_codes.py` 重新產生）。

## 工具

- `list_departments(query="")`：列出系所代碼／系名／學制，可用系名子字串篩選。
- `search_courses(semester, dept, keyword="")`：查某系某學期的開課。
  - `semester`：學年+學期，例如 `1151` = 115 學年第 1 學期。
  - `dept`：系名或三碼代碼（例如 `財務管理學系` 或 `357`）。
  - `keyword`：選填，以關鍵字篩課名／教師／備註。
  - 每門課都附 `syllabus_url`。
- `get_syllabus(syllabus_url)`：讀取某門課的教學大綱全文（課程簡介、課程目標、學習成效、
  每週進度）。僅接受 nccu.edu.tw 網域的連結。

## 安裝

> **在用 Claude Code？** 把這個 repo 的網址貼給它、說「幫我安裝這個 MCP server」，
> 它會讀下面的指令並幫你執行。否則自己複製一行指令即可。

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

## 說明

- 上游伺服器使用舊版 TLS renegotiation，client 開啟 `OP_LEGACY_SERVER_CONNECT` 才連得上。
- 廣域查詢上游有 500 筆上限，因此一律逐系查詢。
- 只用政大公開的課程目錄，不碰任何私有系統、不需登入。
