#!/usr/bin/env python3
"""Regression tests for LinkedIn OAuth readiness and image CLI forwarding.

Offline only: no credential store writes, no network calls, no LinkedIn action.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from unittest import mock

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import linkedin_auth as auth  # noqa: E402
import linkedin_workflow as workflow  # noqa: E402


NOW = dt.datetime(2026, 10, 3, 10, 0, tzinfo=dt.timezone.utc)


def _presence(*, client_id=False, client_secret=False,
              refresh_token=False, access_token=False):
    values = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "access_token": access_token,
    }
    return {
        key: {
            "target": auth.CRED_TARGETS[key],
            "env_var": auth.ENV_VARS[key],
            "present": bool(values[key]),
            "source": "credential_manager" if values[key] else "none",
        }
        for key in auth.CRED_TARGETS
    }


def _ready(pres, expiry):
    with mock.patch.object(auth, "presence", return_value=pres), \
            mock.patch.object(auth, "access_token_expiry", return_value=expiry):
        return auth.oauth_ready(now=NOW), auth.oauth_ready_detail(now=NOW)


def test_valid_access_token_without_refresh_token_is_ready():
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True, access_token=True),
        "2026-12-02T00:26:11Z",
    )
    assert ready is True
    assert detail["usable_access_token"] is True
    assert detail["refresh_path_available"] is False


def test_expired_access_token_with_complete_refresh_path_is_ready():
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True,
                  refresh_token=True, access_token=True),
        "2026-10-02T00:00:00Z",
    )
    assert ready is True
    assert detail["usable_access_token"] is False
    assert detail["refresh_path_available"] is True


def test_expired_access_token_without_refresh_token_is_not_ready():
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True, access_token=True),
        "2026-10-02T00:00:00Z",
    )
    assert ready is False
    assert detail["usable_access_token"] is False
    assert detail["refresh_path_available"] is False


def test_no_access_token_with_complete_refresh_path_is_ready():
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True, refresh_token=True),
        None,
    )
    assert ready is True
    assert detail["usable_access_token"] is False
    assert detail["refresh_path_available"] is True


def test_no_usable_access_token_with_incomplete_refresh_path_is_not_ready():
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True),
        None,
    )
    assert ready is False
    assert detail["usable_access_token"] is False
    assert detail["refresh_path_available"] is False


def test_access_token_with_missing_expiry_fails_closed():
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True, access_token=True),
        None,
    )
    assert ready is False
    assert "expiry is missing or invalid" in detail["reason"]


def test_access_token_inside_safety_skew_is_not_usable():
    expiry = (NOW + dt.timedelta(seconds=auth.ACCESS_TOKEN_SAFETY_SKEW_SECONDS - 1)).isoformat()
    ready, detail = _ready(
        _presence(client_id=True, client_secret=True, access_token=True),
        expiry,
    )
    assert ready is False
    assert detail["usable_access_token"] is False


def test_workflow_forwards_image_argument_to_supported_publisher(tmp_path):
    drafts = tmp_path / "linkedin_drafts.json"
    drafts.write_text(json.dumps({
        "drafts": [{
            "kind": "post",
            "status": "draft_unsent",
            "body": "offline CLI contract",
            "blocked": False,
        }]
    }), encoding="utf-8")
    image = tmp_path / "post.png"
    image.write_bytes(b"not-used-in-this-offline-forwarding-test")

    seen = {}

    def fake_publish_main(argv):
        seen["argv"] = list(argv)
        return 0

    with mock.patch("linkedin_publish.main", side_effect=fake_publish_main):
        code = workflow.main([
            "publish",
            "--drafts", str(drafts),
            "--image", str(image),
            "--dry-run",
        ])

    assert code == 0
    argv = seen["argv"]
    assert argv[0] == "publish"
    assert "--image" in argv
    idx = argv.index("--image")
    assert argv[idx + 1] == str(image)
