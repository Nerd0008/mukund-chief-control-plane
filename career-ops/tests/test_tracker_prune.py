#!/usr/bin/env python3
"""Tracker prune — decisions and ordering, without touching the network.

The failure this pins: the owner asked to "remove the jobs which have expired and
require any clearance or citizenship. Only keep jobs and internships which I have
already applied and are open keep the open ones on top". An earlier cut of the
ordering put every Applied row at the top, because an Applied row whose JD could
not be fetched reads as "not expired" and so fell into the open bucket.

``classify`` fetches each posting, so these tests pre-populate the screening
cache — the seam ``screen()`` reads — rather than hitting the network.
"""

import datetime as dt
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import tracker_prune as tp  # noqa: E402

URL = "https://example.com/job"


def make(status, *, url=URL, deadline=None, hits=(), closed=False, readable=True):
    """A row plus the cache entry ``screen()`` will read for it."""
    r = {"row": 1, "values": [None, "Acme", "Role", url, deadline, status],
         "formats": ["General"] * 6, "url": url, "link_target": url,
         "status": status.strip().lower(), "hits": [], "readable": readable,
         "deadline_passed": False, "expired": False,
         "decision": "keep", "reason": "", "bucket": None}
    cache = {url: {"hits": list(hits), "closed": bool(closed),
                   "readable": bool(readable)}}
    return r, cache


# --- keep / remove decisions ------------------------------------------------ #

def test_clearance_requirement_is_removed_even_when_applied():
    """The instruction is unconditional: a vetting bar disqualifies the row."""
    r, cache = make("Applied", hits=("sc",))
    assert tp.classify([r], cache, 1)[0]["decision"] == "remove"


def test_closed_posting_is_removed():
    r, cache = make("Not Applied", closed=True)
    assert tp.classify([r], cache, 1)[0]["decision"] == "remove"


def test_applied_history_survives_a_closed_posting():
    """Applied rows are the owner's own history, never pruned."""
    r, cache = make("Applied", closed=True)
    assert tp.classify([r], cache, 1)[0]["decision"] == "keep"


def test_rejected_history_survives_a_closed_posting():
    r, cache = make("Rejected", closed=True)
    assert tp.classify([r], cache, 1)[0]["decision"] == "keep"


def test_open_posting_is_kept():
    r, cache = make("Not Applied", closed=False)
    assert tp.classify([r], cache, 1)[0]["decision"] == "keep"


def test_deadline_passed_removes_an_unapplied_row():
    r, cache = make("Not Applied", deadline="2020-01-01")
    assert tp.classify([r], cache, 1)[0]["decision"] == "remove"


def test_deadline_passed_does_not_remove_applied_history():
    r, cache = make("Applied", deadline="2020-01-01")
    assert tp.classify([r], cache, 1)[0]["decision"] == "keep"


# --- ordering --------------------------------------------------------------- #

def test_open_roles_sort_above_applied_and_rejected():
    a, _ = make("Rejected")
    b, _ = make("Applied")
    c, _ = make("Not Applied", closed=False)
    assert [r["status"] for r in tp.order([a, b, c])] == [
        "not applied", "applied", "rejected"]


def test_unverifiable_candidates_sort_with_the_open_block():
    """A row that cannot be checked is kept, not buried under the history."""
    a, _ = make("Applied")
    b, _ = make("Not Applied", closed=True, readable=False)
    c, _ = make("Not Applied", closed=False)
    assert [r["status"] for r in tp.order([a, b, c])] == [
        "not applied", "not applied", "applied"]


def test_rejected_always_sorts_last():
    a, _ = make("Rejected")
    b, _ = make("Applied")
    c, _ = make("Not Applied", closed=False)
    assert tp.order([a, b, c])[-1]["status"] == "rejected"


# --- deadline parsing ------------------------------------------------------- #

def test_deadline_in_the_past_has_passed():
    assert tp.deadline_passed("2020-01-01") is True


def test_deadline_in_the_future_has_not_passed():
    future = (dt.date.today() + dt.timedelta(days=90)).isoformat()
    assert tp.deadline_passed(future) is False


def test_missing_or_unparseable_deadline_does_not_pass():
    assert tp.deadline_passed(None) is False
    assert tp.deadline_passed("") is False
    assert tp.deadline_passed("Rolling") is False


# --- screening -------------------------------------------------------------- #

def test_row_with_no_url_is_unverified_not_removed():
    r, _ = make("Not Applied", url="not-a-url")
    assert tp.classify([r], {}, 1)[0]["readable"] is False


def test_cache_hit_short_circuits_the_fetch():
    """A pre-populated cache entry is returned without any network call."""
    hits, closed, readable = tp.screen(URL, 1, {
        URL: {"hits": ["sc"], "closed": True, "readable": True}})
    assert (hits, closed, readable) == (["sc"], True, True)
