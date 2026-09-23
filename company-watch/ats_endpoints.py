#!/usr/bin/env python3
"""Company Watch — bounded, structured ATS/career-endpoint access.

Design rules
------------
* Structured JSON career/ATS endpoints only. No scraping of rendered pages for
  job data, no browser automation, no owner cookies or signed-in sessions.
* Zero auth, zero LLM tokens, zero provider cost.
* Every request is bounded (timeout + retry cap) and recorded in a call log, so a
  run can be audited and a failure can never be reported as a success.
* A slug guess is **not** attribution evidence. A board is only trusted when the
  vendor payload itself names the company, or when the vendor's board page for
  that slug contains the company name as a standalone token. Anything weaker is
  recorded as ``attribution_confidence: "low"`` with
  ``manual_attribution_required: true`` and is excluded from tracker handoff.

Vendors implemented (all public, unauthenticated JSON):

    greenhouse   boards-api.greenhouse.io/v1/boards/<slug>/jobs
    ashby        api.ashbyhq.com/posting-api/job-board/<slug>
    lever        api.lever.co/v0/postings/<slug>?mode=json
    workable     apply.workable.com/api/v1/widget/accounts/<slug>?details=true
    smartrecruiters  api.smartrecruiters.com/v1/companies/<slug>/postings
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Callable

DEFAULT_USER_AGENT = (
    "chief-company-watch/1.0 (local career automation; contact: repository owner; "
    "structured public ATS endpoints only)"
)

HIGH = "high"
LOW = "low"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

class Fetcher:
    """Bounded HTTP client with an auditable call log. No auth, no cookies."""

    def __init__(self, timeout: float = 20.0, retries: int = 1,
                 user_agent: str = DEFAULT_USER_AGENT):
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        self.calls: list[dict] = []

    def _once(self, url: str) -> tuple[int | None, str, str | None]:
        req = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/html;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            return e.code, "", f"HTTPError {e.code}"
        except Exception as e:  # noqa: BLE001 - recorded, never swallowed
            return None, "", f"{type(e).__name__}: {e}"

    def get(self, url: str) -> tuple[int | None, str, str | None]:
        started = time.time()
        status, body, error = None, "", None
        for attempt in range(self.retries + 1):
            status, body, error = self._once(url)
            if status == 200 or (status is not None and 400 <= status < 500):
                break
            if attempt < self.retries:
                time.sleep(0.5)
        self.calls.append({
            "url": url,
            "status": status,
            "ok": status == 200,
            "error": error,
            "bytes": len(body),
            "duration_s": round(time.time() - started, 2),
        })
        return status, body, error

    def get_json(self, url: str) -> tuple[int | None, object | None, str | None]:
        status, body, error = self.get(url)
        if status != 200:
            return status, None, error or f"HTTP {status}"
        try:
            return status, json.loads(body), None
        except json.JSONDecodeError as e:
            return status, None, f"JSONDecodeError: {e}"

    def summary(self) -> dict:
        return {
            "requests": len(self.calls),
            "ok": sum(1 for c in self.calls if c["ok"]),
            "non_200": sum(1 for c in self.calls if not c["ok"]),
            "total_bytes": sum(c["bytes"] for c in self.calls),
        }


class FakeFetcher:
    """Deterministic offline fetcher used by the test suite.

    ``responses`` maps an exact URL to ``(status, body_text)``. Anything not in
    the map returns 404 — the same shape an unimplemented board produces, so an
    unexpected call can never silently look like a success.
    """

    def __init__(self, responses: dict[str, tuple[int, str]]):
        self.responses = dict(responses)
        self.calls: list[dict] = []

    def get(self, url: str) -> tuple[int | None, str, str | None]:
        status, body = self.responses.get(url, (404, ""))
        self.calls.append({"url": url, "status": status, "ok": status == 200,
                           "error": None if status == 200 else f"HTTP {status}",
                           "bytes": len(body), "duration_s": 0.0})
        return status, body, None if status == 200 else f"HTTP {status}"

    def get_json(self, url: str) -> tuple[int | None, object | None, str | None]:
        status, body, error = self.get(url)
        if status != 200:
            return status, None, error
        try:
            return status, json.loads(body), None
        except json.JSONDecodeError as e:
            return status, None, f"JSONDecodeError: {e}"

    def summary(self) -> dict:
        return {
            "requests": len(self.calls),
            "ok": sum(1 for c in self.calls if c["ok"]),
            "non_200": sum(1 for c in self.calls if not c["ok"]),
            "total_bytes": sum(c["bytes"] for c in self.calls),
        }


# --------------------------------------------------------------------------- #
# vendors
# --------------------------------------------------------------------------- #

def _jobs_from_greenhouse(payload: object, _slug: str) -> list[dict]:
    jobs = (payload or {}).get("jobs", []) if isinstance(payload, dict) else []
    out = []
    for j in jobs:
        out.append({
            "job_id": str(j.get("id")),
            "title": j.get("title"),
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "url_source": "vendor",
            "posted_at": j.get("first_published") or j.get("updated_at"),
            "updated_at": j.get("updated_at"),
        })
    return out


def _company_name_greenhouse(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    names = {j.get("company_name").strip() for j in payload.get("jobs", [])
             if isinstance(j.get("company_name"), str) and j.get("company_name").strip()}
    if len(names) == 1:
        return names.pop()
    return None


def _jobs_from_ashby(payload: object, _slug: str) -> list[dict]:
    jobs = (payload or {}).get("jobs", []) if isinstance(payload, dict) else []
    out = []
    for j in jobs:
        out.append({
            "job_id": str(j.get("id")),
            "title": j.get("title"),
            "location": j.get("location"),
            "url": j.get("jobUrl"),
            "url_source": "vendor",
            "posted_at": j.get("publishedAt"),
            "updated_at": j.get("publishedAt"),
            "listed": j.get("isListed"),
        })
    return [j for j in out if j.get("listed") is not False]


def _jobs_from_lever(payload: object, _slug: str) -> list[dict]:
    if not isinstance(payload, list):
        return []
    out = []
    for j in payload:
        created = j.get("createdAt")
        posted = None
        if isinstance(created, (int, float)) and created > 0:
            import datetime as _dt
            posted = _dt.datetime.fromtimestamp(created / 1000, tz=_dt.timezone.utc).isoformat()
        out.append({
            "job_id": str(j.get("id")),
            "title": j.get("text"),
            "location": (j.get("categories") or {}).get("location"),
            "url": j.get("hostedUrl"),
            "url_source": "vendor",
            "posted_at": posted,
            "updated_at": posted,
        })
    return out


def _jobs_from_workable(payload: object, _slug: str) -> list[dict]:
    jobs = (payload or {}).get("jobs", []) if isinstance(payload, dict) else []
    out = []
    for j in jobs:
        out.append({
            "job_id": str(j.get("shortcode") or j.get("id")),
            "title": j.get("title"),
            "location": j.get("city") or j.get("country") or j.get("location"),
            "url": j.get("url") or j.get("application_url"),
            "url_source": "vendor",
            "posted_at": j.get("published_on") or j.get("created_at"),
            "updated_at": j.get("published_on"),
        })
    return out


def _company_name_workable(payload: object) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("name"), str):
        return payload["name"].strip() or None
    return None


def _jobs_from_smartrecruiters(payload: object, slug: str) -> list[dict]:
    content = (payload or {}).get("content", []) if isinstance(payload, dict) else []
    out = []
    for j in content:
        loc = j.get("location") or {}
        loc_text = ", ".join(str(x) for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
        ref = j.get("ref")
        if isinstance(ref, dict):
            url = ref.get("jobAd") or ref.get("publicUrl")
        else:
            url = ref
        source = "vendor"
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))
                and "api.smartrecruiters.com" not in url):
            # The postings API returns an API URL (or nothing usable). The public
            # posting address follows a documented pattern, but a constructed URL
            # is *not* vendor evidence — it is flagged as derived and must be
            # verified before it can reach a tracker.
            url = f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}"
            source = "derived_pattern"
        out.append({
            "job_id": str(j.get("id")),
            "title": j.get("name"),
            "location": loc_text or None,
            "url": url,
            "url_source": source,
            "posted_at": j.get("releasedDate"),
            "updated_at": j.get("releasedDate"),
        })
    return out


def _company_name_smartrecruiters(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    names = {(j.get("company") or {}).get("name") for j in payload.get("content", [])
             if (j.get("company") or {}).get("name")}
    if len(names) == 1:
        return names.pop()
    return None


VENDORS: dict[str, dict] = {
    "greenhouse": {
        "jobs_url": lambda s: f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
        "page_url": lambda s: f"https://boards.greenhouse.io/{s}",
        "parse": _jobs_from_greenhouse,
        "payload_company_name": _company_name_greenhouse,
        "board_label": lambda s: f"greenhouse board '{s}'",
    },
    "ashby": {
        "jobs_url": lambda s: f"https://api.ashbyhq.com/posting-api/job-board/{s}",
        "page_url": lambda s: f"https://jobs.ashbyhq.com/{s}",
        "parse": _jobs_from_ashby,
        "payload_company_name": lambda _p: None,
        "board_label": lambda s: f"ashby board '{s}'",
    },
    "lever": {
        "jobs_url": lambda s: f"https://api.lever.co/v0/postings/{s}?mode=json",
        "page_url": lambda s: f"https://jobs.lever.co/{s}",
        "parse": _jobs_from_lever,
        "payload_company_name": lambda _p: None,
        "board_label": lambda s: f"lever board '{s}'",
    },
    "workable": {
        "jobs_url": lambda s: f"https://apply.workable.com/api/v1/widget/accounts/{s}?details=true",
        "page_url": lambda s: f"https://apply.workable.com/{s}/",
        "parse": _jobs_from_workable,
        "payload_company_name": _company_name_workable,
        "board_label": lambda s: f"workable account '{s}'",
    },
    "smartrecruiters": {
        "jobs_url": lambda s: f"https://api.smartrecruiters.com/v1/companies/{s}/postings",
        "page_url": lambda s: f"https://jobs.smartrecruiters.com/{s}",
        "parse": _jobs_from_smartrecruiters,
        "payload_company_name": _company_name_smartrecruiters,
        "board_label": lambda s: f"smartrecruiters company '{s}'",
    },
}

#: Vendor order = cheapest/most-likely first. Bounded work per company.
VENDOR_ORDER = ("greenhouse", "ashby", "lever", "workable", "smartrecruiters")


def _variants_match(registry_variants: list[str], candidate: str) -> bool:
    norm = re.sub(r"[^0-9a-z]+", "", (candidate or "").casefold())
    if not norm:
        return False
    return norm in registry_variants


def _page_confirms_name(page_text: str, registry_variants: list[str]) -> bool:
    """Standalone-token containment check on a vendor board page.

    Only variants long enough to be discriminating (>= 5 normalised chars) are
    accepted from a page; short acronyms such as ``EY``/``IBM`` match too much
    text to be evidence, so they are refused here and flagged for manual review.
    """
    text = re.sub(r"<[^>]+>", " ", page_text or "")
    norm_text = re.sub(r"[^0-9a-z]+", " ", text.casefold())
    for variant in registry_variants:
        if len(variant) < 5:
            continue
        if re.search(rf"(?<![0-9a-z]){re.escape(variant)}(?![0-9a-z])", norm_text):
            return True
    return False


def resolve_company(company: dict, fetcher: Fetcher | FakeFetcher, *,
                    vendors: tuple[str, ...] = VENDOR_ORDER,
                    verify_page: bool = True) -> dict:
    """Probe bounded structured endpoints for one registry company.

    Returns a resolution record. ``jobs`` is only populated for a board whose
    attribution is confirmed; an unattributed board is reported as such and its
    jobs are deliberately discarded rather than mis-attributed.
    """
    variants = company.get("name_variants") or []
    slugs = company.get("ats_slug_candidates") or []
    record = {
        "company": company["name"],
        "evidence_class": company.get("evidence_class"),
        "slug_candidates": slugs,
        "attempts": [],
        "resolved": False,
        "vendor": None,
        "board_slug": None,
        "board_url": None,
        "jobs_listed": None,
        "attribution_confidence": None,
        "attribution_basis": None,
        "manual_attribution_required": False,
        "jobs": [],
    }

    for slug in slugs:
        for vendor in vendors:
            spec = VENDORS[vendor]
            url = spec["jobs_url"](slug)
            status, payload, error = fetcher.get_json(url)
            try:
                jobs = spec["parse"](payload, slug) if status == 200 else []
                parse_error = None
            except Exception as exc:  # a malformed payload must not kill the sweep
                jobs, parse_error = [], f"{type(exc).__name__}: {exc}"
            attempt = {"vendor": vendor, "slug": slug, "url": url, "status": status,
                       "jobs": len(jobs), "error": error or parse_error}
            record["attempts"].append(attempt)
            if parse_error:
                attempt["outcome"] = "parse_error"
                continue
            if status != 200 or not jobs:
                attempt["outcome"] = "no_board" if status != 200 else "board_empty"
                continue

            payload_name = spec["payload_company_name"](payload)
            if payload_name and _variants_match(variants, payload_name):
                confidence, basis = HIGH, f"vendor_payload_company_name:{payload_name}"
            else:
                page_status, page_text, _perr = fetcher.get(spec["page_url"](slug))
                if payload_name:
                    confidence = LOW
                    basis = f"vendor_payload_company_name_mismatch:{payload_name}"
                elif _page_confirms_name(page_text, variants):
                    confidence, basis = HIGH, f"board_page_name_match:{spec['page_url'](slug)}"
                else:
                    confidence, basis = LOW, "slug_guess_only"
                if page_status != 200:
                    basis += f";board_page_http_{page_status}"

            attempt["outcome"] = "board_with_jobs"
            attempt["attribution_confidence"] = confidence
            attempt["attribution_basis"] = basis

            candidate = {
                "resolved": True,
                "vendor": vendor,
                "board_slug": slug,
                "board_url": spec["board_label"](slug),
                "jobs_listed": len(jobs),
                "attribution_confidence": confidence,
                "attribution_basis": basis,
                "manual_attribution_required": confidence != HIGH,
            }
            if confidence == HIGH:
                candidate["jobs"] = [{**job, "vendor": vendor, "board_slug": slug}
                                     for job in jobs]
                record.update(candidate)
                record.pop("jobs_discarded_attribution_unconfirmed", None)
                return record
            # Keep the first unattributed board as a provisional record only; keep
            # probing the remaining candidates in case a properly attributable
            # board exists (a guessed slug may collide with an unrelated company).
            if record["attribution_confidence"] is None:
                record.update(candidate)
                record["jobs_discarded_attribution_unconfirmed"] = len(jobs)

    if record["resolved"]:
        return record

    record["manual_attribution_required"] = True
    record["unresolved_reason"] = "no_vendor_board_resolved_via_slug_guess"
    return record


def resolve_companies(companies: list[dict], fetcher, *, limit: int | None = None,
                      budget_s: float | None = None,
                      vendors: tuple[str, ...] = VENDOR_ORDER,
                      verify_page: bool = True,
                      clock: Callable[[], float] = time.time) -> dict:
    """Resolve a bounded slice of companies, honouring a hard wall-clock budget."""
    started = clock()
    resolved, unresolved, budget_exhausted = [], [], False
    sliced = companies[:limit] if limit else list(companies)
    for company in sliced:
        if budget_s is not None and (clock() - started) > budget_s:
            budget_exhausted = True
            break
        rec = resolve_company(company, fetcher, vendors=vendors, verify_page=verify_page)
        (resolved if rec["resolved"] else unresolved).append(rec)
    return {
        "companies_considered": len(sliced),
        "companies_probed": len(resolved) + len(unresolved),
        "resolved": resolved,
        "unresolved": unresolved,
        "budget_s": budget_s,
        "budget_exhausted": budget_exhausted,
        "duration_s": round(clock() - started, 2),
        "http": fetcher.summary(),
    }
