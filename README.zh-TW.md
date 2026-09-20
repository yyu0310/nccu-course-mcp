# NCCU Course MCP

政大選課查詢（qrysub.nccu.edu.tw）的 MCP server，讓 AI Agent 或學生用自然語言查課，
不用再跟難用的網頁介面搏鬥。

**不知道從哪開始？** 把這段貼給你的 AI Coding Agent（如 Claude Code、Codex 等）：

> 幫我安裝這個 MCP server
> https://github.com/yyu0310/nccu-course-mcp

它自己就能跑完下面幾乎所有步驟，只有一個密碼相關的步驟要你自己動手。Claude Code
跟 Claude Desktop（桌面 App）都可以用，這兩個都跑在你自己的電腦上。網頁版 claude.ai
跟手機 App 沒辦法跑本機 MCP server，所以不能用這個。

課程資料每次查詢都**即時**打政大公開課程 API，不存本地課程資料庫。唯一附帶的資料檔是
`dept_codes.json`（系所代碼對中文系名的 snapshot，隨時可用 `build_dept_codes.py` 重新產生）。

## 工具

你不需要記住下面任何一支工具的名字或參數，直接跟 AI Agent 說你想查什麼（例如「幫我
查財管系開的課」「這堂課會不會跟我禮拜三下午的課衝堂」），它會自己挑對的工具呼叫。
這張表是給想知道背後在做什麼的人看的。

| 功能 | 做什麼 | 什麼時候會用到 | 工具名稱 |
|---|---|---|---|
| 全校彈性查課 | 用關鍵字搜課名、教師、備註、課號，可再用星期、授課語言、必選修、核心通識、教師名縮小範圍 | 不確定課掛在哪個系所 | `search_all` |
| 衝堂檢查 | 給一串課號，回傳衝突明細＋週課表；備註裡的 TA 實習課時間會自動併入檢查 | 排好課表要確認會不會撞課 | `check_schedule` |
| 開課單位代碼表 | 列出系所、整開科目、通識、體育、學分學程的代碼，可用名稱篩選 | 不確定某個系所的代碼或全名怎麼寫 | `list_departments` |
| 查某系開課 | 查某個開課單位某學期的開課清單 | 已經知道要查哪個系所 | `search_courses` |
| 教學大綱全文 | 課程簡介、課程目標、學習成效、每週進度 | 選課前想看課程細節 | `get_syllabus` |
| 教學評量查詢（選用） | 某位教師近六學期的評量分數＋學生文字意見（依政大規定僅開放近六學期） | 想知道某老師教學評價如何，**需要你自己的政大帳密**，密碼隱私機制請見下方說明 | `get_course_rating` |

其餘工具一律匿名、不需登入，只有教學評量查詢例外。

每門課都回結構化欄位：`slots`（節次清單，衝堂判斷不用解析「三CD78」）、`note_facts`
（備註抽取：實習課時間／會考日期／優先系／加簽限制／英語授課）、`syllabus_url`。
查詢配方與選課領域知識見 [QUERY_GUIDE.md](QUERY_GUIDE.md)。

## 安裝

> **AI Agent 在幫忙裝這個？** 這節的指令直接自己跑，不用先問人類。跑到下面「選用
> 功能」那節之前先停下來讀一遍說明，裡面有一步絕對不能代替人類做。

### 推薦：免 clone、免建 venv（需要 [uv](https://docs.astral.sh/uv/)）

直接從 GitHub 跑，給 Claude Code。

**步驟 0：確認有 `uvx`。** 執行 `uvx --version`，找不到指令就裝一次 uv，再載入
目前的 shell（安裝程式會放在 `~/.local/bin`，那個資料夾一開始不在 PATH 裡）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
```

**步驟 1：註冊 server。**

```bash
claude mcp add nccu-course -- uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp
```

第一次跑 `claude mcp list` 健康檢查要下載並建置套件，需要 10 到 60 秒。如果顯示
「Failed to connect」，而你的編輯器或桌面 App 啟動 Claude Code 時沒吃到新的 PATH，
改用完整路徑重新註冊：`claude mcp add nccu-course -- ~/.local/bin/uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp`。

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
uv run --with keyring python -c "import keyring; keyring.set_password('nccu-ldap', '<你的學號>', input())"
```

（`uv run --with keyring` 會臨時抓 `keyring` 給這一條指令用，不用事先安裝。需要
安裝章節裡的 `uv`。）

它會問你密碼，輸入時畫面不顯示字元。這用的是 `keyring` 這個套件，macOS
（Keychain）已驗證可用，Windows（認證管理員）、Linux（Secret Service）理論上
是同一條指令，但我沒實測過。密碼
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

## 延伸閱讀

不只對這個工具陌生，對 Claude Code 本身也是新手？[claude-code-security-starter](https://github.com/yyu0310/claude-code-security-starter)
是一份 CLAUDE.md 規則＋hooks 的起手式，在憑證外洩發生前就攔下來，很適合當第一個安裝的專案。
