# AGENTS.md — NCCU Course MCP

Context for AI assistants working on this repo.

## What this is

A local (stdio) MCP server that queries NCCU's course-listing API
(`es.nccu.edu.tw`, backing qrysub.nccu.edu.tw) and exposes six tools:
`search_all`, `check_schedule`, `list_departments`, `search_courses`,
`get_syllabus`, `get_course_rating`. Live-only: no local course database.

`get_course_rating` is the one login-required tool: it needs the caller's own
NCCU credentials (`NCCU_STUDENT_ID` env var + macOS Keychain password) to
temporarily add a course to the account's tracking list, since that is the
only way to obtain the teacher's internal rating-page id. Everything else is
anonymous, public data.

Design principle: sink model intelligence into deterministic code (structured
`slots`, `note_facts` mining, conflict checking) so weak models get the same
answer quality as strong ones. Tool docstrings carry the query guide; they are
the only documentation every MCP client is guaranteed to see. NEVER build a
docstring by string concatenation (`"""...""" + X`): it silently becomes
`__doc__ = None` and the tool registers with no description (test 6g guards this).

## Layout

- `src/nccu_course_mcp/server.py`: FastMCP entry (`main()`), the six tools, dept resolution.
- `src/nccu_course_mcp/client.py` — legacy-TLS HTTP session, `search_raw()`, `normalize()`, `fetch_syllabus()`.
- `src/nccu_course_mcp/rate.py`: login, tracking-list add/read/delete, rating-page fetch and parse. Backs `get_course_rating` only, every other tool ignores it.
- `src/nccu_course_mcp/dept_codes.json` — department code↔name snapshot (loaded at import).
- `src/nccu_course_mcp/build_dept_codes.py` — regenerate the snapshot by scanning live.
- `src/nccu_course_mcp/test_server.py`: functional self-test (hits live API); the `get_course_rating` section skips itself when `NCCU_STUDENT_ID` is unset.

## Run / test

```bash
python -m venv .venv && ./.venv/bin/pip install -e .
./.venv/bin/python src/nccu_course_mcp/test_server.py                             # core tools only
NCCU_STUDENT_ID=<your id> ./.venv/bin/python src/nccu_course_mcp/test_server.py   # plus rating tool
```

## Gotchas (don't undo these)

- **Legacy TLS**: the upstream needs `OP_LEGACY_SERVER_CONNECT`; Python's default SSL
  rejects it. The adapter in `client.py` handles it; keep it.
- **500-row cap**: broad queries (omitting `dp3`) are truncated at 500 rows upstream.
  Always query per department (`dp3`), never school-wide in one call.
- **Query shape**: `sem` + `dp3` is enough; `dp1`/`dp2` are optional. For regular
  departments, `dp3` = first 3 digits of a course id = the department code.
- **dp3 is NOT always the course-id prefix** (2026-07-17 bug): school-wide units use
  their own dp3 code spaces: 整開/通識 (107=經濟學, 2S4=社會科學類通識; course ids start
  `000`), 學分學程 (P01–P79), 體育/國防 (6S1/7S1), plus alphanumeric college codes
  (ZU1, ZC0, NU1, 1T3…). The authoritative code tree is the qrysub frontend static file
  `https://qrysub.nccu.edu.tw/assets/api/unit.json` (17 L1 units / L2 level / L3 = dp3).
  `build_dept_codes.py` scans that whole tree; the hardcoded NAME dict is fallback only.
- **Same name, two codes**: a department name can map to both an undergrad and a
  graduate code (e.g. 財務管理學系 = 307 and 357). `_resolve_dept` refuses to guess.
- `fetch_syllabus` is host-restricted to `*.nccu.edu.tw`; keep that check (trust boundary).
- **Keep `mcp<2` pinned in `pyproject.toml`**: mcp 2.x renamed `FastMCP` to `MCPServer` and moved the
  import, so `from mcp.server.fastmcp import FastMCP` fails at startup. A fresh `uvx` install resolves the
  newest mcp and the server dies with "Connection closed". Migrate to the 2.x API before lifting the pin.
- **`rate.get_trace_all_data` must be called without a semester segment**: the semester-suffixed
  URL `tracing/{lang}/{sem}/{encstu}/` returns the right record count but every field null, this
  is server-side behavior, not a bug on our end. The plain `tracing/{lang}/{encstu}/` returns real
  values and already targets the caller's current tracked semester.
- **`teaStatUrl` points at a frameset shell, not the data**: it is `statisticAll.jsp-tnum=X`, a
  page with two empty `<frame>`s. The real table lives in the embedded frame `statistic.jsp-tnum=X`
  (same URL, one word shorter). `rate.fetch_rating` does a plain string replace before fetching.

## Updating the department snapshot

`python src/nccu_course_mcp/build_dept_codes.py 1151`: pass the target semester; it
rescans live and rewrites `dept_codes.json`.
