"""NCCU teaching evaluation (教學意見調查) lookup. Optional, login-required extension.

Reverse-engineered from qrysub's frontend (myServer=es.nccu.edu.tw). Flow:
  login(student_id, password) -> encstu          # POST person/
  resolve_tea_stat_url(encstu, course)            # track course -> read teaStatUrl -> untrack
  fetch_rating(tea_stat_url)                      # public GET statistic.jsp -> parsed table

Credential handling:
  - Password: OS credential store only (`keyring`, cross-platform), never touches disk in plaintext.
  - Student ID: `NCCU_STUDENT_ID` environment variable.
  - All logging redacts password and encstu (encstu is a 30-minute JWT session token).
"""
import logging
import os
import re
from urllib.parse import quote

try:  # run directly (tests) or as an installed package
    import client
except ImportError:
    from nccu_course_mcp import client

log = logging.getLogger("nccu_course_mcp.rate")
MYSERVER = "https://es.nccu.edu.tw"
DEFAULT_LANG = "zh-TW"


def get_student_id() -> str:
    """Read the caller's student ID from the NCCU_STUDENT_ID env var."""
    sid = os.environ.get("NCCU_STUDENT_ID", "")
    if not sid:
        raise RuntimeError("NCCU_STUDENT_ID not set. Export it or add it to your MCP client's env config.")
    return sid


def get_password(student_id: str) -> str:
    """Read the NCCU portal password from the OS credential store via `keyring`
    (service=nccu-ldap, account=student_id). `keyring` picks the right backend on its own:
    macOS Keychain, Windows Credential Manager, or Linux Secret Service.
    Set it once with: uv run --with keyring python -c "import keyring; keyring.set_password('nccu-ldap', '<id>', input())"
    """
    import keyring
    pw = keyring.get_password("nccu-ldap", student_id)
    if not pw:
        raise RuntimeError(
            "No credential store entry. Set it with: uv run --with keyring python -c \"import keyring; "
            f"keyring.set_password('nccu-ldap', '{student_id}', input())\""
        )
    return pw


def _redact(s: str, keep: int = 0) -> str:
    """Mask a secret for logging."""
    if not s:
        return "<empty>"
    return s[:keep] + "…" + f"[{len(s)} chars redacted]"


def _encode_uri_component(s: str) -> str:
    """Mirror JS encodeURIComponent (leaves A-Za-z0-9-_.!~*'() unescaped)."""
    return quote(s, safe="!~*'()")


def _sanitize_cred(s: str) -> str:
    """Mirror the frontend's checkLdapParam: / -> ／(U+FF0F), \\ -> ＼(U+FF3C). Not encryption."""
    return s.replace("/", "／").replace("\\", "＼")


def login(student_id: str, password: str) -> str:
    """POST es.nccu.edu.tw/person/{urlencode(sanitize(id+"!!)"+password))}/ -> encstu.
    Raises on failure (encstu=="ERROR" or unexpected response shape)."""
    payload = _sanitize_cred(f"{student_id}!!){password}")
    url = f"{MYSERVER}/person/{_encode_uri_component(payload)}/"
    log.info("POST login person/  (id=%s, password=%s)", student_id, _redact(password))
    r = client._session.post(url, data="", timeout=20)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data or "encstu" not in data[0]:
        raise RuntimeError(f"Unexpected login response shape: {str(data)[:120]}")
    encstu = data[0]["encstu"]
    if encstu == "ERROR" or not encstu:
        raise RuntimeError("Login failed: wrong student ID or password (encstu=ERROR)")
    log.info("  <- login OK encstu=%s", _redact(encstu))
    return encstu


def get_trace_all_data(encstu: str, lang: str = DEFAULT_LANG) -> list[dict]:
    """Read the caller's tracked-course list (each record includes teaStatUrl).
    Must call WITHOUT a semester segment in the URL: `tracing/{lang}/{encstu}/`.
    The semester-suffixed variant `tracing/{lang}/{sem}/{encstu}/` returns the right
    record count but every field null; this is server-side behavior, not a client bug."""
    url = f"{MYSERVER}/tracing/{lang}/{encstu}/"
    log.info("POST read tracking list %s", url.replace(encstu, _redact(encstu)))
    r = client._session.post(url, data="", timeout=20)
    r.raise_for_status()
    data = r.json()
    log.info("  <- %d tracked record(s)", len(data) if isinstance(data, list) else -1)
    return data if isinstance(data, list) else []


def _add_key(course: dict) -> str:
    """Build the tracking-add key: flag "1" + 9-digit course id."""
    course_id = course.get("course_id") or course.get("subNum") or ""
    return f"1{course_id}"


def add_to_tracing(encstu: str, course: dict, lang: str = DEFAULT_LANG) -> None:
    """POST tracing/C/{lang}/{flag}{course_id}-{encstu}/  add one course to the tracking list."""
    key = _add_key(course)
    url = f"{MYSERVER}/tracing/C/{lang}/{key}-{encstu}/"
    log.info("POST track %s", key)
    r = client._session.post(url, data="", timeout=20)
    r.raise_for_status()


def delete_from_tracing(encstu: str, course: dict, lang: str = DEFAULT_LANG) -> None:
    """Undo: remove from the tracking list, so lookups don't pollute the account's real list."""
    key = course.get("course_id") or course.get("subNum") or ""
    url = f"{MYSERVER}/tracing/D/{lang}/{key}-{encstu}/"
    log.info("POST untrack %s", key)
    try:
        client._session.post(url, data="", timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001  best-effort cleanup, non-fatal
        log.warning("Untrack cleanup failed (non-fatal): %s", e)


def resolve_tea_stat_url(encstu: str, course: dict,
                         lang: str = DEFAULT_LANG, cleanup: bool = True) -> str | None:
    """Track the course, read the tracking list for its teaStatUrl, then untrack. Returns the
    URL, or None if the course has no rating history yet (e.g. teacher's first time teaching it)."""
    course_id = course.get("course_id") or course.get("subNum") or ""
    add_to_tracing(encstu, course, lang)
    try:
        for rec in get_trace_all_data(encstu, lang):
            rid = rec.get("subNum") or rec.get("course_id") or ""
            if rid in (None, "None"):
                continue
            if rid == course_id or rid.startswith(course_id[:9]):
                url = rec.get("teaStatUrl")
                return url if url and url != "None" else None
        return None
    finally:
        if cleanup:
            delete_from_tracing(encstu, course, lang)


def fetch_rating(tea_stat_url: str, with_comments: bool = True) -> dict:
    """GET the evaluation history table (public, no login needed) and parse it.
    teaStatUrl points at statisticAll.jsp, a frameset shell (opening it directly shows two
    empty <frame>s). The actual data table lives in the embedded frame statistic.jsp, same URL
    one word shorter; swap it in before fetching.
    When with_comments is True (default), also fetches each row's written comments (one extra
    GET per row that has any); set False to skip that and get scores only, faster."""
    if not re.match(r"^https?://[\w.-]*\.nccu\.edu\.tw/", tea_stat_url):
        raise ValueError(f"Only nccu.edu.tw URLs accepted: {tea_stat_url[:80]}")
    content_url = tea_stat_url.replace("statisticAll.jsp", "statistic.jsp")
    log.info("GET rating page %s", content_url)
    r = client._session.get(content_url, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    result = _parse_statistic(r.text, content_url)
    if with_comments:
        for row in result["rows"]:
            row["comments"] = fetch_comments(row["comment_url"], content_url) if row["comment_url"] else []
    return result


def fetch_comments(comment_url: str, base_url: str) -> list[str]:
    """GET one course's written comments (public, no login needed) and return them as a list
    of strings. comment_url is the relative href from the rating table; resolve it against the
    rating page's own URL first."""
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup
    full_url = urljoin(base_url, comment_url)
    r = client._session.get(full_url, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table", attrs={"border": "1"})
    if not tables:
        return []
    return [td.get_text(strip=True) for td in tables[-1].find_all("td")]


def _parse_statistic(html: str, url: str = "") -> dict:
    """Parse statistic.jsp's evaluation history table.
    Fixed 9 columns (year, semester, course_id, course_name, enrolled, responded,
    response_rate, score, comment link), header row identified by bgcolor="#FFFFCC". Numeric
    columns are converted; the comment column becomes a URL plus count when a text-comment
    link exists, otherwise the raw label (e.g. "no comments")."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "")
    teacher = ""
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if text.startswith("任課教師："):
            teacher = text.removeprefix("任課教師：").strip()
            break

    data_table = None
    for table in soup.find_all("table"):
        header = table.find("tr", attrs={"bgcolor": "#FFFFCC"})
        if header:
            data_table = table
            break

    rows = []
    if data_table:
        for tr in data_table.find_all("tr"):
            if tr.get("bgcolor") == "#FFFFCC":
                continue  # header row
            cells = tr.find_all("td")
            if len(cells) != 9:
                continue
            link = cells[8].find("a")
            if link:
                comment = {"comment_url": link.get("href", ""),
                           "comment_count": cells[8].get_text(strip=True).strip("()")}
            else:
                comment = {"comment_url": None, "comment_count": cells[8].get_text(strip=True)}
            rows.append({
                "year": cells[0].get_text(strip=True),
                "semester": cells[1].get_text(strip=True),
                "course_id": cells[2].get_text(strip=True),
                "course_name": cells[3].get_text(strip=True),
                "enrolled": int(cells[4].get_text(strip=True) or 0),
                "responded": int(cells[5].get_text(strip=True) or 0),
                "response_rate": cells[6].get_text(strip=True),
                "score": float(cells[7].get_text(strip=True) or 0),
                **comment,
            })
    return {"source_url": url, "title": title, "teacher": teacher, "rows": rows}


if __name__ == "__main__":
    # Pure-function checks only (no login, no network).
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    assert _sanitize_cred("a/b\\c") == "a／b＼c"
    assert _encode_uri_component("a!b)c d") == "a!b)c%20d"
    p = _sanitize_cred("A1234!!)pw/1")
    u = f"{MYSERVER}/person/{_encode_uri_component(p)}/"
    assert u.startswith("https://es.nccu.edu.tw/person/") and "／" not in u
    assert _redact("secret123") == "…[9 chars redacted]"
    print("OK: pure-function tests passed (sanitize/encode/redact/login-url)")
