# AGENTS.md — NCCU Course MCP

Context for AI assistants working on this repo.

## What this is

A local (stdio) MCP server that queries NCCU's course-listing API
(`es.nccu.edu.tw`, backing qrysub.nccu.edu.tw) and exposes five tools:
`search_all`, `check_schedule`, `list_departments`, `search_courses`,
`get_syllabus`. Live-only: no local course database.

Design principle: sink model intelligence into deterministic code (structured
`slots`, `note_facts` mining, conflict checking) so weak models get the same
answer quality as strong ones. Tool docstrings carry the query guide; they are
the only documentation every MCP client is guaranteed to see. NEVER build a
docstring by string concatenation (`"""...""" + X`): it silently becomes
`__doc__ = None` and the tool registers with no description (test 6g guards this).

## Layout

- `src/nccu_course_mcp/server.py` — FastMCP entry (`main()`), the five tools, dept resolution.
- `src/nccu_course_mcp/client.py` — legacy-TLS HTTP session, `search_raw()`, `normalize()`, `fetch_syllabus()`.
- `src/nccu_course_mcp/dept_codes.json` — department code↔name snapshot (loaded at import).
- `src/nccu_course_mcp/build_dept_codes.py` — regenerate the snapshot by scanning live.
- `src/nccu_course_mcp/test_server.py` — functional self-test (hits live API).

## Run / test

```bash
python -m venv .venv && ./.venv/bin/pip install -e .
./.venv/bin/python src/nccu_course_mcp/test_server.py
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

## Updating the department snapshot

`python src/nccu_course_mcp/build_dept_codes.py 1151`: pass the target semester; it
rescans live and rewrites `dept_codes.json`.
