#!/usr/bin/env python3
"""Fetch and extract plain text from a job posting URL.

Used by both the daily digest and the nightly pipeline to read full JDs
before the clearance/eligibility gates run. No browser, no login, no
JavaScript — just HTTP GET + HTML-to-text extraction.

Returns a dict with:
  - url: the URL that was fetched
  - status: HTTP status code
  - text: extracted plain text (or empty string on failure)
  - error: error message (or None)
  - fetch_state: one of "validated_live", "bot_wall", "fetch_failed"
"""
from __future__ import annotations

import re
from application_deadlines import extract_application_deadline
import urllib.error
import urllib.request
from urllib.parse import urlparse

MAX_BYTES = 512 * 1024  # 512 KB cap
TIMEOUT = 30  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Tags whose content is typically the main job body
CONTENT_SELECTORS = (
    "article", "main", "[role=main]",
    ".job-description", ".job-description__content",
    ".description", ".details", ".details-body",
    "#job-description", "#jobDescription",
    ".posting-content", ".posting-content__text",
    ".ats-description", ".ats-job-description",
    ".greenhouse-job-description",
    "[data-testid=job-description]",
    ".jobsearch-JobComponent-description",
    ".job-details", ".job-details-body",
)

# Tags to strip before extraction
STRIP_TAGS = (
    "script", "style", "nav", "header", "footer",
    "form", "button", "select", "input", "textarea",
    "svg", "canvas", "video", "audio", "iframe",
    "noscript", "template",
)


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML without external dependencies."""
    # Remove strip tags and their content
    for tag in STRIP_TAGS:
        html = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    # Replace <br>, <p>, <div>, <li>, <tr>, <h1-6> with newlines
    html = re.sub(
        r"<(?:br|/p|/div|/li|/tr|/h[1-6]|/section|/article)\b[^>]*>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )
    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    html = (
        html.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&#x27;", "'")
        .replace("&#x2F;", "/")
        .replace("&ndash;", "–")
        .replace("&mdash;", "—")
    )
    # Collapse whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n\s*\n", "\n\n", html)
    return html.strip()


def fetch_jd(url: str) -> dict:
    """Fetch a job posting URL and return extracted text.

    Returns a dict with keys: url, status, text, error, fetch_state.
    """
    result = {
        "url": url,
        "status": None,
        "text": "",
        "error": None,
        "fetch_state": "fetch_failed",
        "deadline": None,
        "deadline_info": extract_application_deadline("", url),
    }

    if not url or not url.lower().startswith(("http://", "https://")):
        result["error"] = "not a valid HTTP URL"
        return result

    parsed = urlparse(url)
    if not parsed.hostname:
        result["error"] = "no hostname in URL"
        return result

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result["status"] = resp.status
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html = raw.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                html = raw.decode("utf-8", errors="replace")
            result["text"] = _html_to_text(html)
            result["fetch_state"] = "validated_live"
            result["deadline_info"] = extract_application_deadline(result["text"], url)
            result["deadline"] = result["deadline_info"]["date"]
            result["is_closed"] = is_job_closed(result["text"])
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        if e.code in (403, 429):
            result["fetch_state"] = "bot_wall"
            result["error"] = f"HTTP {e.code} (bot wall)"
        else:
            result["error"] = f"HTTP {e.code}"
    except urllib.error.URLError as e:
        result["error"] = f"URL error: {e.reason}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


# ---------------------------------------------------------------------------
# deadline + liveness extraction
# ---------------------------------------------------------------------------

_CLOSED_PATTERNS = [
    re.compile(r"\b(?:position|role)\s+(?:has\s+)?been\s+filled\b", re.I),
    re.compile(r"\b(?:no\s+longer\s+accepting|closed\s+for\s+applications)\b", re.I),
    re.compile(r"\b(?:deadline\s+has\s+passed|application\s+period\s+has\s+ended)\b", re.I),
    re.compile(r"\bthis\s+(?:job|vacancy|role)\s+has\s+(?:closed|expired)\b", re.I),
    re.compile(r"\bwe\s+are\s+no\s+longer\s+accepting\s+applications\b", re.I),
    re.compile(r"\bapplications\s+are\s+now\s+closed\b", re.I),
]

def extract_deadline(text: str):
    """Compatibility date-only API; structured JD deadline extraction is authoritative."""
    return extract_application_deadline(text)['date']


def is_job_closed(text: str) -> bool:
    """Check if the job page indicates the position is closed or filled."""
    return any(p.search(text) for p in _CLOSED_PATTERNS)


def fetch_jds(urls: list[str], *, timeout: int = TIMEOUT) -> list[dict]:
    """Fetch multiple job URLs, return list of result dicts."""
    results = []
    for url in urls:
        results.append(fetch_jd(url))
    return results
