"""Fail-closed scheduled bootstrap for an independently configured queue clone.

Configuration is local/non-secret; absence never falls back to the shared tree.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid
from datetime import datetime, timezone

DEFAULT_CONFIG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'hermes/remote-queue/poller.json'


def load_config(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    paths = {}
    for name in ('repo_root', 'shared_repo_root', 'runtime_dir', 'python_executable'):
        raw = Path(data[name])
        if not raw.is_absolute():
            raise ValueError('configuration paths must be absolute')
        paths[name] = raw.resolve()
    root, shared, runtime = (paths[k] for k in ('repo_root', 'shared_repo_root', 'runtime_dir'))
    if root == shared or root.is_relative_to(shared) or shared.is_relative_to(root):
        raise ValueError('poller checkout must be separate from shared checkout')
    if runtime.is_relative_to(root) or runtime.is_relative_to(shared):
        raise ValueError('poller runtime must be outside both checkouts')
    if not (root / '.git').is_dir() or not (root / 'remote_queue/poller.py').is_file():
        raise ValueError('independent poller clone required')
    if not paths['python_executable'].is_file():
        raise ValueError('configured Python unavailable')
    branch = data['branch']
    if branch in ('main', 'master') or not branch or branch.startswith('-'):
        raise ValueError('feature queue branch required')
    origin = data['origin']
    if not origin or ('://' in origin and '@' in origin.split('://', 1)[1].split('/')[0]):
        raise ValueError('credential-free origin required')
    def git(*args):
        result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                                timeout=30, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        if result.returncode:
            raise ValueError('configured checkout Git validation failed')
        return result.stdout.strip()
    if (root / git('rev-parse', '--git-common-dir')).resolve() != root / '.git':
        raise ValueError('shared Git metadata forbidden')
    if git('symbolic-ref', '--short', 'HEAD') != branch:
        raise ValueError('configured branch mismatch')
    if git('remote', 'get-url', 'origin') != origin:
        raise ValueError('configured origin mismatch')
    if git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}') != 'origin/' + branch:
        raise ValueError('configured upstream mismatch')
    return {**data, **paths}


def run(config_path, check_only=False):
    config = load_config(config_path)
    root, runtime = config['repo_root'], config['runtime_dir']
    runtime.mkdir(parents=True, exist_ok=True)
    env = {**os.environ,
           'HERMES_REPO_ROOT': str(root), 'HERMES_QUEUE_ROOT': str(root / 'remote-queue'),
           'HERMES_SHARED_REPO_ROOT': str(config['shared_repo_root']),
           'HERMES_QUEUE_BRANCH': config['branch'],
           'HERMES_POLLER_RUNTIME_DIR': str(runtime),
           'HERMES_QUEUE_LOG_ROOT': str(runtime / 'logs'),
           'HERMES_REMOTE_VISIBLE': '0', 'PYTHONUTF8': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'GIT_TERMINAL_PROMPT': '0'}
    command = [str(config['python_executable']), str(root / 'remote_queue/poller.py'),
               '--check-only' if check_only else '--once']
    record = {'timestamp': datetime.now(timezone.utc).isoformat(),
              'repo_root': str(root), 'shared_repo_root': str(config['shared_repo_root']),
              'runtime_dir': str(runtime), 'branch': config['branch'],
              'command': command, 'check_only': check_only,
              'principal': os.environ.get('USERDOMAIN', '') + '\\' + os.environ.get('USERNAME', '')}
    try:
        result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                timeout=150 if check_only else 3900,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record['exit_code'] = result.returncode
        # No task bodies, auth output or provider diagnostics go into evidence.
        for line in reversed(result.stdout.splitlines()):
            try:
                report = json.loads(line)
                if isinstance(report, dict) and 'status' in report:
                    record['result'] = report
                    break
            except ValueError:
                continue
    except subprocess.TimeoutExpired:
        record.update(exit_code=1, result={'status': 'bootstrap_timeout', 'dispatches': 'unknown'})
    target = runtime / ('last-check.json' if check_only else 'last-run.json')
    temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps(record))
    return record['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        return run(args.config, args.check_only)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        print(json.dumps({'status': 'configuration_blocked', 'exit_code': 1, 'dispatches': 0}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
