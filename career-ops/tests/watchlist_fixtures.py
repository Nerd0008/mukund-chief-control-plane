#!/usr/bin/env python3
"""Offline fixtures for the owner-company priority watchlist lane (roster B27).

Two things live here, and nothing else:

1. the synthetic watchlist + Company Watch fixtures are read from
   ``fixtures/discovery/watchlist/`` (every company, title and URL invented, every
   host on the reserved ``.invalid`` TLD);
2. :func:`build_capture` builds a *captured research document* for the lane's OWN
   generated query matrix — the same shape ``web_research.CapturedResultsProvider``
   emits — so the lane can be exercised end-to-end with no network access at all.

Building the capture from the lane's own matrix (rather than committing hashed
query ids) means the fixture can never drift from the query generator: if the
matrix changes, the capture follows it.

Nothing here touches the network, a workbook, an account or a real employer.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # career-ops/tests
CAREER_OPS = HERE.parent
CONTROL_PLANE = CAREER_OPS.parent
for _p in (str(CAREER_OPS), str(CAREER_OPS / "discovery")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import web_research as wr  # noqa: E402
import watchlist as wl  # noqa: E402

FIXTURE_DIR = HERE / "fixtures" / "discovery" / "watchlist"
INPUT_FIXTURE = FIXTURE_DIR / "watchlist-input.json"
COMPANY_WATCH_OVERLAP = FIXTURE_DIR / "company-watch-overlap.json"

#: The one vacancy three surfaces see (the watchlist lane, Company Watch and — for
#: the careers/ATS family — the employer's own board result).
SHARED_VACANCY_URL = "https://overlap-test.invalid/jobs/soc-analyst-l1"

#: Hosts the fake validator treats as reachable. Everything else fails validation,
#: which is what a genuinely unreachable company looks like.
LIVE_HOSTS = (
    "fixture-security.invalid",
    "fixture-security.teamtailor.invalid",
    "fixture-security-group.wd1.myworkdayjobs.invalid",
    "job-boards.greenhouse.invalid",
    "overlap-test.invalid",
    "quiet-roles.invalid",
)


def load_input_fixture(path: Path | None = None) -> dict:
    return json.loads(Path(path or INPUT_FIXTURE).read_text(encoding="utf-8"))


def load_companies(path: Path | None = None) -> list:
    """The canonical companies for the fixture watchlist."""
    loaded = wl.load_watchlist_input(Path(path or INPUT_FIXTURE))
    return wl.build_identity(loaded["companies"])["companies"]


def _live(url: str, title: str, description: str | None = None) -> dict:
    return {"url": url, "canonical_url": wr.canonical_url(url),
            "status": wr.FETCH_VALIDATED_LIVE, "http_status": 200, "final_url": url,
            "page_title": title, "meta_description": description, "content_chars": 4096,
            "robots": "test", "expired_marker": None, "error": None,
            "fetched_at": "2026-09-24T06:00:00+00:00"}


def _failed(url: str, reason: str = "HTTP 404") -> dict:
    return {"url": url, "canonical_url": wr.canonical_url(url),
            "status": wr.FETCH_VALIDATION_FAILED, "http_status": 404, "final_url": url,
            "page_title": None, "meta_description": None, "content_chars": 0,
            "robots": "test", "expired_marker": None, "error": reason,
            "fetched_at": "2026-09-24T06:00:00+00:00"}


def fake_fetch(url: str, **kwargs) -> dict:
    """Deterministic stand-in for ``web_research.fetch_validate``.

    ``fixture-security.invalid`` and ``overlap-test.invalid`` serve their own careers
    pages (and name themselves on them); the two discovered ATS hosts serve posting
    pages that name their company; everything else is unreachable — which is exactly
    how an inaccessible careers page behaves.
    """
    host = (urllib.parse.urlparse(str(url or "")).hostname or "").casefold()
    if not any(h in host for h in LIVE_HOSTS):
        return _failed(url)
    if "teamtailor" in host:
        return _live(url, "SOC Analyst L1 — Fixture Security Ltd",
                     "Fixture Security Ltd is hiring a SOC Analyst L1 in London.")
    if "myworkdayjobs" in host:
        return _live(url, "Early Careers Analyst — Fixture Security Group",
                     "Fixture Security Group early careers programme in London.")
    if "greenhouse" in host:
        return _live(url, "SOC Analyst L1 @ Fixture Security Ltd",
                     "Fixture Security Ltd (London) SOC Analyst L1.")
    if "fixture-security.invalid" in host and url.rstrip("/").endswith("/careers"):
        return _live(url, "Careers at Fixture Security Ltd",
                     "Fixture Security Ltd careers: graduate and SOC roles.")
    if "quiet-roles.invalid" in host:
        return _live(url, "Careers at Quiet Roles Ltd",
                     "Quiet Roles Ltd careers: our current openings.")
    if "overlap-test.invalid" in host and url.rstrip("/").endswith("/careers"):
        return _live(url, "Careers at Overlap Test Ltd",
                     "Overlap Test Ltd careers: SOC Analyst roles.")
    if "fixture-security.invalid" in host:
        return _live(url, "SOC Analyst L1 @ Fixture Security Ltd",
                     "Fixture Security Ltd, London — SOC Analyst L1.")
    if "overlap-test.invalid" in host:
        return _live(url, "SOC Analyst L1 | Overlap Test Ltd",
                     "Overlap Test Ltd, London — SOC Analyst L1.")
    return _failed(url)


#: The results the fake research worker returns, keyed by (company, query family,
#: surface or role family). Deliberately minimal: one company gets an ATS-discovered
#: careers surface, one gets a duplicated vacancy, one gets only a keyword-listing
#: page, and one gets nothing at all.
def _results_for(query: dict) -> list:
    company = query["watchlist_company"]
    family = query["query_family"]
    scope = query["surface_scope"]
    role_family = query["role_family"]
    if company == "Fixture Security Ltd":
        if family == wl.FAMILY_CAREERS and scope == "teamtailor":
            return [{"title": "Fixture Security Ltd — Careers",
                     "url": "https://fixture-security.teamtailor.invalid/jobs/1",
                     "snippet": "Fixture Security Ltd careers on Teamtailor."}]
        if family == wl.FAMILY_CAREERS and scope == "greenhouse":
            return [{"title": "SOC Analyst L1 @ Fixture Security Ltd",
                     "url": "https://job-boards.greenhouse.invalid/fixture-security/jobs/401",
                     "snippet": "Fixture Security Ltd SOC Analyst L1."}]
        if family == wl.FAMILY_ROLE and role_family == "soc_security_operations":
            return [{"title": "SOC Analyst L1 | Fixture Security Ltd",
                     "url": "https://fixture-security.invalid/jobs/soc-analyst-l1",
                     "snippet": "Fixture Security Ltd, London — SOC Analyst L1."}]
        return []
    if company == "Fixture Security Group":
        if family == wl.FAMILY_CAREERS and scope == "workday":
            return [{"title": "Early Careers Analyst — Fixture Security Group",
                     "url": ("https://fixture-security-group.wd1.myworkdayjobs.invalid/"
                             "en-US/careers/job/1"),
                     "snippet": "Fixture Security Group early careers programme."}]
        return []
    if company == "Overlap Test Ltd":
        if family == wl.FAMILY_ROLE and role_family == "watchlist_cross_family":
            return [{"title": "SOC Analyst L1 — Overlap Test Ltd",
                     "url": SHARED_VACANCY_URL,
                     "snippet": "Overlap Test Ltd, London — SOC Analyst L1."}]
        return []
    if company == "No Surface Co":
        # The only discovery is the board's own keyword-listing page: not a vacancy,
        # and the host is unreachable, so the company stays unavailable/unknown.
        if family == wl.FAMILY_CAREERS:
            return [{"title": "900+ Cyber Security Graduate Jobs in London",
                     "url": "https://no-surface.invalid/jobs/cyber-security-jobs-in-london",
                     "snippet": "Keyword listing page."}]
        return []
    # "Quiet Roles Ltd": a resolved careers surface and zero matching roles.
    return []


def build_capture(companies: list, region: str = "uk") -> dict:
    """A captured research document covering the lane's own query matrix."""
    queries = [q for c in companies for q in wl.build_company_queries(c, region)]
    return {
        "_fixture": ("Synthetic capture for the priority-watchlist lane. Built from the lane's "
                     "own generated query matrix; every URL uses the reserved .invalid TLD and no "
                     "record describes a real vacancy or employer."),
        "not_a_real_vacancy": True,
        "kind": wr.EXPORT_KIND,
        "schema_version": 1,
        "export_id": "watchlist-fixture0001",
        "captured_from": "captured",
        "captured_at": "2026-09-24T06:00:00Z",
        "provider": {"provider": "captured", "available": True, "limitation": None,
                     "requests": len(queries), "cli_version": None,
                     "web_search_observed_queries": len(queries),
                     "queries_without_observed_search": 0},
        "queries": [{**q, "executed": True, "web_search_observed": True,
                     "executed_queries": [q["query"]], "results": _results_for(q),
                     "error": None}
                    for q in queries],
    }


def write_lane_fixture(tmp_path: Path, *, region: str = "uk", companies: list | None = None) -> dict:
    """Run the whole lane offline (fake fetcher + fake validator + captured results).

    Returns ``{"companies", "capture_path", "lane"}``. Writes only under ``tmp_path``.
    """
    companies = companies if companies is not None else load_companies()
    identity = wl.build_identity([{**row, "_index": i}
                                  for i, row in enumerate(
                                      load_input_fixture().get("companies") or [])])
    capture_path = Path(tmp_path) / "watchlist-capture.json"
    capture_path.write_text(json.dumps(build_capture(companies, region), indent=2),
                            encoding="utf-8")
    provider = wr.CapturedResultsProvider(capture_path)
    lane = wl.run_lane(companies, region=region, provider=provider,
                       fetcher=FakeFetcher(), page_validator=fake_fetch,
                       validate_fn=fake_fetch, max_urls_per_company=200)
    lane["watchlist"].update({"path": str(INPUT_FIXTURE), "present": True, "readable": True,
                              "malformed_rows": [], "limitation": None,
                              "identity": {"merges": identity["merges"],
                                           "merge_rules": identity["merge_rules"],
                                           "duplicate_spellings_collapsed":
                                               identity["duplicate_spellings_collapsed"]}})
    return {"companies": companies, "capture_path": str(capture_path), "lane": lane,
            "identity": identity}


class FakeFetcher:
    """Deterministic offline fetcher: every host is unreachable by default.

    A company with a reachable public structured board would answer here; the fixture
    set deliberately contains none, so *every* careers surface in the fixture comes
    from the owner-supplied URL or from the research lane's discovery — which is the
    behaviour under test.
    """

    def __init__(self, responses: dict | None = None):
        self.responses = dict(responses or {})
        self.calls: list[dict] = []

    def get(self, url: str):
        status, body = self.responses.get(url, (404, ""))
        self.calls.append({"url": url, "status": status, "ok": status == 200,
                           "error": None if status == 200 else f"HTTP {status}",
                           "bytes": len(body), "duration_s": 0.0})
        return status, body, (None if status == 200 else f"HTTP {status}")

    def get_json(self, url: str):
        status, body, error = self.get(url)
        if status != 200:
            return status, None, error
        try:
            return status, json.loads(body), None
        except json.JSONDecodeError as exc:
            return status, None, f"JSONDecodeError: {exc}"

    def summary(self) -> dict:
        return {"requests": len(self.calls),
                "ok": sum(1 for c in self.calls if c["ok"]),
                "non_200": sum(1 for c in self.calls if not c["ok"]),
                "total_bytes": sum(c["bytes"] for c in self.calls)}


def structured_board_fetcher(slug: str, *, company_name: str) -> FakeFetcher:
    """A fake fetcher that answers ONE attributed Greenhouse board.

    Proves the structured ATS route (the 5 vendors Company Watch implements) without
    any network access.
    """
    jobs_payload = json.dumps({"jobs": [
        {"id": 401, "title": "Graduate SOC Analyst", "absolute_url":
         f"https://job-boards.greenhouse.invalid/{slug}/jobs/401",
         "company_name": company_name, "updated_at": "2026-09-20T09:00:00Z",
         "location": {"name": "London, United Kingdom"}}]})
    return FakeFetcher({
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs": (200, jobs_payload),
        f"https://boards.greenhouse.io/{slug}": (200, f"<html><title>{company_name}</title></html>"),
    })


def unattributed_board_fetcher(slug: str) -> FakeFetcher:
    """A board that answers but never names the company: attribution must stay LOW."""
    jobs_payload = json.dumps({"jobs": [
        {"id": 9, "title": "Analyst", "absolute_url": f"https://unrelated.invalid/{slug}/9",
         "company_name": "Some Unrelated Company (NOT THE OWNER'S TARGET)",
         "location": {"name": "London"}}]})
    return FakeFetcher({
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs": (200, jobs_payload),
        f"https://boards.greenhouse.io/{slug}": (200, "<html><title>Careers</title></html>"),
    })


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
