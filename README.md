# NCCU Course MCP

An MCP server for querying NCCU (National Chengchi University) course listings
(qrysub.nccu.edu.tw) programmatically — so an AI assistant or a student can search
courses in plain language instead of fighting the web UI.

Course data is fetched **live** from the public course API on every query; there is
no local course database. The only shipped data file is `dept_codes.json`, a snapshot
mapping department codes to names (regenerate any time with `build_dept_codes.py`).

## Tools

- `list_departments(query="")` — list department codes/names/levels; filter by a name substring.
- `search_courses(semester, dept, keyword="")` — courses for a department in a term.
  - `semester`: academic-year + term, e.g. `1151` = AY115 term 1.
  - `dept`: department name or 3-digit code (e.g. `財務管理學系` or `357`).
  - `keyword`: optional; filter by course name / teacher / notes.
  - each course includes a `syllabus_url`.
- `get_syllabus(syllabus_url)` — fetch a course's full syllabus as plain text
  (description, objectives, learning outcomes, weekly schedule). Restricted to
  nccu.edu.tw URLs.

## Install

> **Using Claude Code?** Paste this repo's URL and say *"install this MCP server"* —
> Claude Code will read the command below and run it for you. Otherwise, copy one command.

### Recommended — no clone, no venv (needs [uv](https://docs.astral.sh/uv/))

Runs straight from GitHub for Claude Code:

```bash
claude mcp add nccu-course -- uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp
```

Don't have `uv`? Install it once: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### No-uv fallback — pip only

Works with any Python 3.10+ (uses `pipx` to keep it isolated):

```bash
pipx install git+https://github.com/yyu0310/nccu-course-mcp
claude mcp add nccu-course -- nccu-course-mcp
```

Or add to any MCP client's config (e.g. Claude Desktop `claude_desktop_config.json`):

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

### From source

```bash
git clone https://github.com/yyu0310/nccu-course-mcp && cd nccu-course-mcp
python -m venv .venv && ./.venv/bin/pip install -e .
./.venv/bin/python src/nccu_course_mcp/test_server.py   # live self-test
claude mcp add nccu-course -- ./.venv/bin/nccu-course-mcp
```

## Notes

- The upstream server uses legacy TLS renegotiation; the client enables
  `OP_LEGACY_SERVER_CONNECT` to connect.
- Broad queries are capped at 500 rows upstream, so queries are always scoped per
  department.
- Public course-catalog data only — this is not an exploit of any private system.
