"""Cross-process admission and observed backoff for bounded Codex calls.

Only one physical call per model is admitted at once. File locks are released
by the OS on process exit. State contains no objectives, output or credentials.
"""
from contextlib import contextmanager
from pathlib import Path
import datetime, hashlib, json, math, os, re, time, uuid

ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'hermes/runtime/router-brain/codex-admission'


class AdmissionBlocked(RuntimeError):
    def __init__(self, kind, *, retry_after_seconds=None, request_dispatched=False):
        super().__init__(kind)
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds
        self.request_dispatched = request_dispatched


def rate_limit_signal(stdout='', stderr='', *, now=None):
    """Recognize transport status, not arbitrary numbers in a prompt/trace ID."""
    def text(v):
        return v.decode('utf-8', errors='replace') if isinstance(v, bytes) else str(v or '')
    instant = time.time() if now is None else now
    for line in reversed(text(stderr).splitlines()):
        if not re.search(r'\b(?:last status:|HTTP(?:/\S+)?\s*|status(?: code)?[:=]?\s*)429\b|\b429 Too Many Requests\b', line, re.I):
            continue
        wait = re.search(r'retrying sampling request\s*\(\d+/\d+ in\s+([\d.]+)s\)', line)
        delay = float(wait.group(1)) if wait else 30.0
        observed = instant
        stamp = re.match(r'^(\d{4}-\d\d-\d\dT[0-9:.]+Z)\s', line)
        if stamp:
            try:
                parsed = datetime.datetime.fromisoformat(stamp.group(1).replace('Z', '+00:00')).timestamp()
                if 0 <= instant-parsed <= 86400:
                    observed = parsed
            except ValueError:
                pass
        until = observed + min(max(delay, 1), 86400)
        return {'http_status': 429, 'retry_after_seconds': max(1, math.ceil(until-instant)),
                'not_before': max(instant+1, until)}
    # Structured terminal errors are allowed; assistant/hidden reasoning is not inspected.
    for line in text(stdout).splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get('type') in ('error', 'turn.failed'):
            error = event.get('error') or event
            if isinstance(error, dict) and error.get('status') == 429:
                return {'http_status': 429, 'retry_after_seconds': 30, 'not_before': instant+30}
    return None


def _paths(model):
    ROOT.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(model).encode()).hexdigest()[:24]
    return ROOT/(key+'.lock'), ROOT/(key+'.json')


def _lock(handle):
    handle.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle):
    handle.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def admit(model, *, timeout, cancel_event=None):
    from workflow_control import ProcessCancelled
    started = time.monotonic()
    lock_path, state_path = _paths(model)
    handle = lock_path.open('a+b')
    locked = False
    try:
        while not locked:
            if cancel_event is not None and cancel_event.is_set():
                raise ProcessCancelled()
            if time.monotonic()-started >= timeout:
                raise AdmissionBlocked('BUSY')
            try:
                _lock(handle)
                locked = True
            except OSError:
                time.sleep(min(.05, max(.001, timeout-(time.monotonic()-started))))
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            until = float(state.get('not_before', 0))
            if not math.isfinite(until) or until<0:raise ValueError('invalid cooldown')
        except (OSError, ValueError, TypeError):
            raise AdmissionBlocked('STATE_UNAVAILABLE') from None
        if until > time.time():
            raise AdmissionBlocked('RATE_LIMITED', retry_after_seconds=math.ceil(until-time.time()))
        yield state_path, max(0, timeout-(time.monotonic()-started))
    finally:
        if locked:
            _unlock(handle)
        handle.close()


def record_backoff(path, signal):
    data = {'not_before': signal['not_before'], 'http_status': 429, 'updated_at': time.time()}
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(data), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def run(command, *, model, timeout, cancel_event=None, **kwargs):
    from workflow_control import run_process
    import subprocess
    with admit(model, timeout=timeout, cancel_event=cancel_event) as (state_path, remaining):
        try:
            # Production operations carry cancellation. Observe their stderr so
            # a 197s CLI retry sleep cannot masquerade as a 45/90s router timeout.
            result = run_process(command, timeout=remaining, cancel_event=cancel_event,
                **({'stop_on_stderr': lambda line: rate_limit_signal(stderr=line) is not None}
                   if cancel_event is not None else {}), **kwargs)
        except subprocess.TimeoutExpired as exc:
            signal = rate_limit_signal(exc.output, exc.stderr)
            if not signal:
                raise
            record_backoff(state_path, signal)
            raise AdmissionBlocked('RATE_LIMITED', retry_after_seconds=signal['retry_after_seconds'], request_dispatched=True) from None
        signal = rate_limit_signal(result.stdout, result.stderr)
        if signal:
            record_backoff(state_path, signal)
            raise AdmissionBlocked('RATE_LIMITED', retry_after_seconds=signal['retry_after_seconds'], request_dispatched=True)
        return result
