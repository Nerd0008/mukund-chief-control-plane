"""Non-destructive Git rules shared by queue synchronization/publication."""
import os
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def target(run):
    rc, branch, _ = run(['symbolic-ref', '--quiet', '--short', 'HEAD'])
    if rc or not branch:
        raise ValueError('queue publication requires a named branch')
    expected = os.environ.get('HERMES_QUEUE_BRANCH')
    if expected and expected != branch:
        raise ValueError('queue branch differs from configured branch')
    rc, remote, _ = run(['config', '--get', f'branch.{branch}.remote'])
    if rc or remote != 'origin':
        raise ValueError('queue branch requires an origin upstream')
    rc, merge, _ = run(['config', '--get', f'branch.{branch}.merge'])
    if rc or merge != f'refs/heads/{branch}':
        raise ValueError('queue upstream must match the current branch')
    rc, url, _ = run(['remote', 'get-url', 'origin'])
    if rc:
        raise ValueError('queue origin unavailable')
    # Local bare origins support offline tests; never publish main/master to
    # a network origin through this queue helper.
    if branch in ('main', 'master') and ('://' in url or ('@' in url and ':' in url)):
        raise ValueError('queue publication to network main/master is forbidden')
    return branch


def isolated(root, run):
    root = Path(root).resolve()
    protected = Path(os.environ.get('HERMES_SHARED_REPO_ROOT') or SOURCE_ROOT).resolve()
    if (root == protected or root.is_relative_to(protected) or protected.is_relative_to(root)
            or not (root / '.git').is_dir() or (root / '.git').is_symlink()):
        return False
    rc, common, _ = run(['rev-parse', '--git-common-dir'])
    return rc == 0 and (root / common).resolve() == (root / '.git').resolve()


def published(run, branch):
    rc, head, _ = run(['rev-parse', 'HEAD'])
    rc2, remote, _ = run(['ls-remote', '--exit-code', 'origin', f'refs/heads/{branch}'])
    if rc or rc2 or not remote:
        return False
    if remote.split()[0] == head:
        return True
    # Another writer may have appended after our successful push. Verify our
    # commit is contained, rather than pretending the wrong ref was updated.
    rc, _, _ = run(['fetch', 'origin', branch])
    return rc == 0 and run(['merge-base', '--is-ancestor', head, f'origin/{branch}'])[0] == 0