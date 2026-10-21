import datetime as dt
import io
import json
import urllib.error

import pytest
import career_google_auth as auth


@pytest.fixture
def vault(monkeypatch):
    values = {v: 'PRIVATE_TEST_VALUE' for v in auth.TARGETS.values()}
    values[auth.TARGETS['token_state']] = json.dumps({
        'scopes': list(auth.SCOPES),
        'expires_at': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()})
    monkeypatch.setattr(auth, 'read_secret', values.get)
    def save(k, v):
        values[k] = v
        return True
    monkeypatch.setattr(auth, 'store_secret', save)
    return values


def successful_refresh(*args, **kwargs):
    return {'access_token': 'NEW_PRIVATE_TEST_VALUE', 'expires_in': 3600}


def test_presence_is_not_readiness(vault):
    result = auth.status()
    assert result['credentials_present'] and result['refresh_token_present']
    assert not result['oauth_ready'] and not result['refresh_verified']
    assert 'PRIVATE_TEST_VALUE' not in json.dumps(result)


def test_live_refresh_then_cached_access(vault, monkeypatch):
    calls = []
    def refresh(*args, **kwargs):
        calls.append(1)
        return successful_refresh()
    monkeypatch.setattr(auth, 'http_json', refresh)
    assert auth.status(verify=True)['oauth_ready']
    assert auth.access_token() == 'NEW_PRIVATE_TEST_VALUE'
    assert len(calls) == 1


@pytest.mark.parametrize('reason,code', [('invalid_grant', 400), (None, None), ('forbidden', 403)])
def test_failed_refresh_is_not_ready(vault, monkeypatch, reason, code):
    def fail(*a, **k):
        raise auth.GoogleError('request', code, reason)
    monkeypatch.setattr(auth, 'http_json', fail)
    result = auth.status(verify=True)
    assert not result['oauth_ready'] and not result['refresh_verified']
    assert result['failure_reason'] == (reason or 'refresh_failed')
    assert not auth.status()['oauth_ready']


def test_revocation_does_not_hammer_google(vault, monkeypatch):
    calls = []
    def fail(*a, **k):
        calls.append(1)
        raise auth.GoogleError('request', 400, 'invalid_grant')
    monkeypatch.setattr(auth, 'http_json', fail)
    auth.status(verify=True)
    with pytest.raises(auth.GoogleError):
        auth.access_token()
    assert len(calls) == 1


def test_missing_refresh_token(vault, monkeypatch):
    vault.pop(auth.TARGETS['refresh_token'])
    monkeypatch.setattr(auth, 'http_json', lambda *a, **k: pytest.fail('network called'))
    assert not auth.status(verify=True)['oauth_ready']
    assert not auth.status()['refresh_token_present']


@pytest.mark.parametrize('expiry', ['2000-01-01T00:00:00Z', 'malformed', None, '2099-01-01T00:00:00'])
def test_expired_or_invalid_expiry_refreshes(vault, monkeypatch, expiry):
    saved = json.loads(vault[auth.TARGETS['token_state']])
    saved.update(expires_at=expiry, refresh_verified_at='2026-01-01T00:00:00Z')
    vault[auth.TARGETS['token_state']] = json.dumps(saved)
    assert not auth.status()['oauth_ready']
    monkeypatch.setattr(auth, 'http_json', successful_refresh)
    assert auth.access_token() == 'NEW_PRIVATE_TEST_VALUE'
    assert auth.status()['oauth_ready']


@pytest.mark.parametrize('error', ['invalid_grant', {'errors': [{'reason': 'rateLimitExceeded'}]}])
def test_oauth_and_api_error_shapes_are_safe(monkeypatch, error):
    class Opener:
        def open(self, *a, **k):
            raise urllib.error.HTTPError('https://example.invalid', 400, 'error', {},
                io.BytesIO(json.dumps({'error': error, 'error_description': 'PRIVATE_TEST_VALUE'}).encode()))
    monkeypatch.setattr(auth.urllib.request, 'build_opener', lambda *a: Opener())
    with pytest.raises(auth.GoogleError) as caught:
        auth.http_json('POST', auth.TOKEN_URL)
    assert caught.value.reason in {'invalid_grant', 'rateLimitExceeded'}
    assert 'PRIVATE_TEST_VALUE' not in str(caught.value)


def test_new_consent_clears_old_revocation_but_needs_refresh(vault):
    saved = json.loads(vault[auth.TARGETS['token_state']])
    saved['failure_reason'] = 'invalid_grant'
    vault[auth.TARGETS['token_state']] = json.dumps(saved)
    auth.save_tokens({**successful_refresh(), 'scope': ' '.join(auth.SCOPES), 'refresh_token': 'NEW_REFRESH'})
    assert auth.status()['failure_reason'] == 'refresh_not_verified'
