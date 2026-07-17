# 查詢指南 Query Guide

給 AI agent 與開發者的使用手冊。核心設計目標：**把選課領域知識下沉到工具層**，讓不同能力的模型（Haiku 到 Opus）查出來的結果品質一致。

## 工具速查

| 想做什麼 | 用哪個工具 |
|---|---|
| 不知道課在哪個單位、只有模糊意圖 | `search_all(semester, keyword=...)` 全校搜 |
| 知道單位，看整個單位的開課 | `search_courses(semester, dept)` |
| 找單位代碼 | `list_departments(query)` |
| 排課表、驗證會不會衝堂 | `check_schedule(semester, course_ids, extra_times)` |
| 看評分方式、每週進度、先修要求 | `get_syllabus(syllabus_url)` |

## 選課領域知識（查不到課先看這裡）

政大課程分兩個代碼空間，這是最常見的踩坑點：

1. **系所課**：dp3 代碼＝課號前 3 碼＝系所碼。財管系大學部 307、研究所 357。
2. **全校共同課**：課號 000 開頭，dp3 是「科目代碼」，跟課號無關。
   - 大一大二共同必修（經濟學 107、統計學 106、初級會計學 113、微積分 137、大學英文在外文中心）掛「整開」
   - 通識掛 2S1-2S8（`core_ge` 欄位標核心/一般）
   - 體育必修 6S1、體育選修 6S2、全民國防 7S1
   - 學分學程 P01-P79、輔系專班 3S1-3S8

不確定掛哪就 `search_all` 用 keyword 全校搜，伺服器端會搜課名、教師名、備註、完整課號。

## 常用查詢配方

```python
search_all("1151", keyword="賽局")                      # 意圖搜索：全校跟賽局有關的課
search_all("1151", teacher="郭力昕")                    # 某老師開的所有課（teacher 可單獨用）
search_all("1151", keyword="000219541")                 # 完整 9 碼課號精準反查
search_all("1151", keyword="經濟學", week="3", language="中文")  # 週三的中文經濟學
search_all("1151", dept="通識", core_ge="是", week="2") # 週二核心通識（'通識'自動展開 2S1-2S8）
check_schedule("1151", ["000359021", "000219541"], extra_times=["五EFG"])  # 衝堂＋打工時段
```

群組別名（`dept=` 可傳）：`通識`（2S1-2S8）、`整開`、`體育`、`學分學程`、`輔系`，一次查完整組並去重。

## 排課表標準流程

1. 每個需求科目用 `search_all` 或 `search_courses` 拉候選班。
2. 看 `note_facts.priority` 挑該生所屬系的優先/灌檔班（選課保障最高）。
3. 把候選課號丟 `check_schedule` 驗衝堂。`note_facts.ta_time`（實習課）會自動併入檢查，不用手算。
4. 有 `note_facts.has_ta_session` 但沒有時間的課，用 `get_syllabus` 查大綱有沒有寫 TA 時段。
5. `note_facts.exam` 標會考/考試日期，同日多場要提醒使用者。

## 為什麼弱模型也能用（設計說明）

模型會犯的錯，工具直接做掉（22 人格 QA 驗證：Haiku 也能 5/5 達成）：

- **時間解析**：「三CD78」由 `slots` 欄位回結構化清單，模型不用解析。
- **備註暗雷**：「財管一灌檔」「實習課為四、78」「會考」「不開放加簽」「會一甲限修」由 `note_facts`（priority/ta_time/exam/restriction/no_add/english_taught）抽成欄位。
- **衝堂判斷**：`check_schedule` 決定性計算，含 TA 時段自動併入、學碩合開辨識（`cross_listed`）、時間未定給 `warnings`，模型只負責挑課。
- **關鍵字雜訊**：短英文字（如 'AI'）伺服器會放水回一堆無關課，`matched` 欄位標明命中欄位、截斷時自動濾掉驗證不到的雜訊。
- **假象截斷**：無條件查詢直接報錯；廣域超限回 `truncated=True` + `warnings`，不靜默漏課。
- **型別一致**：`credits` 回數字、`list_departments` 明示回 list、空大綱回明確提示而非空字串。

## 已知限制

- 資料即時打政大 API（live-only），學校改課表這裡就是新的；但 `dept_codes.json` 是 snapshot，換學期要重跑 `build_dept_codes.py`。
- `search_all` 不給任何條件時會命中 500 筆上限，一定要帶條件。
- 課程餘額要另開 `remain_url`，工具未展開。
