# NCCU Course MCP

An MCP server for querying NCCU (National Chengchi University) course listings
(qrysub.nccu.edu.tw) programmatically, so an AI agent or a student can search
courses in plain language instead of fighting the web UI.

**Not sure where to start?** Paste this to your AI coding agent (Claude Code,
Codex, etc.):

> Install this MCP server
> https://github.com/yyu0310/nccu-course-mcp

It can run every step below on its own, except one password step later in
this page that only you should type. Works with Claude Code and the Claude
Desktop app (both run on your own machine). The claude.ai web app and mobile
app can't run local MCP servers like this one, so they're not an option here.

Course data is fetched **live** from the public course API on every query. There is
no local course database. The only shipped data file is `dept_codes.json`, a snapshot
mapping department codes to names (regenerate any time with `build_dept_codes.py`).

## Tools

You don't need to remember any tool name or parameter, just tell your AI agent
what you want (e.g. "find me courses offered by the Finance department" or
"does this course clash with my Wednesday afternoon class"), and it picks the
right tool on its own. This table is for anyone curious what happens under
the hood.

| What it does | Details | When you'd reach for it | Tool name |
|---|---|---|---|
| School-wide flexible search | Keyword search across course names, teachers, notes, and course ids, narrowable by weekday, language, requirement kind, core-GE, or exact teacher | You don't know which department offers a course | `search_all` |
| Schedule conflict check | Give a list of course ids, get back conflicts plus a weekly grid. TA session times are folded in automatically | Checking whether your picked courses collide | `check_schedule` |
| Department code lookup | Lists every offering-unit code (departments, school-wide subjects, general ed, PE, credit programs), filterable by name | You don't know a department's code or exact name | `list_departments` |
| Courses by department | Course list for one offering unit in one semester | You already know which department to search | `search_courses` |
| Full syllabus | Description, objectives, learning outcomes, weekly schedule | Deciding whether to take a course | `get_syllabus` |
| Teaching ratings (optional) | A teacher's evaluation scores and written comments for the last six semesters (NCCU policy caps this window) | Checking a teacher's evaluation history, **needs your own NCCU login**, password privacy explained below | `get_course_rating` |

Every other tool is anonymous and needs no login, the ratings tool is the one exception.

Every course comes with structured fields: `slots` (parsed period list, so models
never hand-parse strings like `三CD78`) and `note_facts` (facts mined from the
free-text notes: TA session time, exam dates, department priority, add-restriction,
English-taught). Query recipes and domain knowledge live in [QUERY_GUIDE.md](QUERY_GUIDE.md).

## Install

> **AI agent doing this install?** Run the command in this section yourself,
> no need to ask the human for anything yet. Stop before the "Optional" section
> below and read its instructions first, that section has one step you must
> never run on the human's behalf.

### Recommended: no clone, no venv (needs [uv](https://docs.astral.sh/uv/))

Runs straight from GitHub for Claude Code.

**Step 0: make sure `uvx` exists.** Run `uvx --version`. If the command is not
found, install uv once, then load it into the current shell (the installer puts
it in `~/.local/bin`, which is not on PATH yet):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
```

**Step 1: register the server.**

```bash
claude mcp add nccu-course -- uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp
```

The first `claude mcp list` health check downloads and builds the package, so
it can take 10 to 60 seconds. If it shows "Failed to connect" and your editor
or GUI app launched Claude Code without the new PATH, re-register with the full
path: `claude mcp add nccu-course -- ~/.local/bin/uvx --from git+https://github.com/yyu0310/nccu-course-mcp nccu-course-mcp`.

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
the one exception: NCCU only shows a teacher's rating history to logged-in
students, so this tool needs your own NCCU login. Skip this whole section if
you don't need it, everything else works unaffected.

### Step 1 (you do this yourself, not your AI agent)

Save your NCCU portal password to your computer's credential store, once.
**If an AI agent is helping you install this, do not let it run this command
or type your password for you.** Open your own terminal and run it yourself:

```bash
uv run --with keyring python -c "import keyring; keyring.set_password('nccu-ldap', '<your student id>', input())"
```

(`uv run --with keyring` fetches `keyring` for this one command, so nothing
needs installing first. It needs the `uv` from the Install section.)

It will ask for your password and hide what you type. This uses `keyring`,
which is verified on macOS (Keychain). Windows (Credential Manager) and
Linux (Secret Service) should work the same way in theory, but I haven't
tested them. Your password never touches disk in plaintext and
is never logged, by this tool or by whatever agent is helping you set it up.

### Step 2 (your AI agent can do this for you)

Tell it your student ID (not a secret, just needed to know whose tracking
list to use) and have it set `NCCU_STUDENT_ID` wherever the server runs, for
example in the MCP client config:

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

## Notes

- The upstream server uses legacy TLS renegotiation. The client enables
  `OP_LEGACY_SERVER_CONNECT` to connect.
- Broad queries are capped at 500 rows upstream, so queries are always scoped per
  department.
- Uses only NCCU's public course catalog and requires no login, except for the
  optional `get_course_rating` tool described above.

## Further reading

New to Claude Code itself, not just this tool? [claude-code-security-starter](https://github.com/yyu0310/claude-code-security-starter)
is a starter pack of CLAUDE.md rules and hooks that block credential leaks before they happen, a good first project to install.
