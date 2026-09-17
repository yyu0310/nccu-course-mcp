# NCCU Course MCP

An MCP server for querying NCCU (National Chengchi University) course listings
(qrysub.nccu.edu.tw) programmatically, so an AI assistant or a student can search
courses in plain language instead of fighting the web UI.

Course data is fetched **live** from the public course API on every query; there is
no local course database. The only shipped data file is `dept_codes.json`, a snapshot
mapping department codes to names (regenerate any time with `build_dept_codes.py`).

## Tools

- `search_all(semester, keyword="", week="", language="", dept="", kind="", core_ge="", teacher="")`:
  school-wide flexible search. The keyword is matched server-side against course
  names, teachers, notes, and full course ids; narrow further by weekday, teaching
  language, requirement kind, core-GE flag, or exact teacher. Use this when you
  don't know which unit offers a course.
- `check_schedule(semester, course_ids, extra_times=[])`: deterministic conflict
  check. Give full course ids; returns conflicts + a weekly grid. TA session times
  mined from course notes are included automatically.
- `list_departments(query="")`: list offering-unit codes (departments, school-wide
  subjects, general education, PE, credit programs); filter by a name substring.
- `search_courses(semester, dept, keyword="")`: courses for one offering unit.
  - `semester`: academic-year + term, e.g. `1151` = AY115 term 1.
  - `dept`: unit name or code (e.g. `財務管理學系`, `357`, or `107` = school-wide Economics).
- `get_syllabus(syllabus_url)`: fetch a course's full syllabus as plain text
  (description, objectives, learning outcomes, weekly schedule). Restricted to
  nccu.edu.tw URLs.
- `get_course_rating(semester, course_id="", teacher="", course_name="")`:
  a teacher's teaching-evaluation history for the last six semesters (NCCU
  policy caps this window), score plus written comments per semester.
  **Optional, needs your own NCCU login**, see below. Every other tool is
  anonymous.

Every course comes with structured fields: `slots` (parsed period list, so models
never hand-parse strings like `三CD78`) and `note_facts` (facts mined from the
free-text notes: TA session time, exam dates, department priority, add-restriction,
English-taught). Query recipes and domain knowledge live in [QUERY_GUIDE.md](QUERY_GUIDE.md).

## Install

> **Using Claude Code?** Paste this repo's URL and say *"install this MCP server"*,
> and it will read the command below and run it for you. Otherwise, copy one command.

### Recommended: no clone, no venv (needs [uv](https://docs.astral.sh/uv/))

Runs straight from GitHub for Claude Code:

```bash
claude mcp add nccu-course -- uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp
```

Don't have `uv`? Install it once: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### No-uv fallback: pip only

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

## Optional: course ratings (`get_course_rating`)

Every other tool is anonymous and needs nothing set up. `get_course_rating` is
the one exception: NCCU only exposes a teacher's rating history to logged-in
students, so this tool needs your own NCCU credentials. It never leaves your
machine, it logs in, briefly tracks the target course to read its rating-page
link, untracks it, then fetches the (public) rating page.

1. Save your NCCU portal password to your OS credential store, once. This uses
   `keyring`, which works the same way on macOS (Keychain), Windows
   (Credential Manager), and Linux (Secret Service):
   ```bash
   python3 -c "import keyring; keyring.set_password('nccu-ldap', '<your student id>', input())"
   ```
2. Set `NCCU_STUDENT_ID` wherever you run the server, for example in the MCP
   client config:
   ```json
   {
     "mcpServers": {
       "nccu-course": {
         "command": "uvx",
         "args": ["--from", "git+https://github.com/yyu0310/nccu-course-mcp", "nccu-course-mcp"],
         "env": { "NCCU_STUDENT_ID": "<your student id>" }
       }
     }
   }
   ```

Your password never touches disk in plaintext and is never logged. Skip both
steps if you don't need this tool, everything else works unaffected.

## Notes

- The upstream server uses legacy TLS renegotiation; the client enables
  `OP_LEGACY_SERVER_CONNECT` to connect.
- Broad queries are capped at 500 rows upstream, so queries are always scoped per
  department.
- Uses only NCCU's public course catalog and requires no login, except for the
  optional `get_course_rating` tool described above.
