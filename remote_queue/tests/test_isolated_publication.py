"""Real disposable Git regressions; no live queues, workers or network origins."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from remote_queue import configured_poller as cp, poller, queue_schema as qs
from remote_queue.tests.test_queue import _make_disposable_repo, _run_git
from remote_queue.tests.test_worker_retry import _make_task


class IsolatedPublication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='poller-isolation-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = _make_disposable_repo(self.base)
        _run_git(['switch', '-c', 'fix/queue-isolation'], self.root)
        _run_git(['push', '-u', 'origin', 'fix/queue-isolation'], self.root)
        for name, value in {
            'REPO_ROOT': self.root, 'QUEUE_DIR': self.root/'remote-queue',
            'PENDING_DIR': self.root/'remote-queue/pending',
            'RUNNING_DIR': self.root/'remote-queue/running',
            'COMPLETED_DIR': self.root/'remote-queue/completed',
            'BLOCKED_DIR': self.root/'remote-queue/blocked',
            'LOG_DIR': self.base/'runtime/logs',
        }.items():
            p = patch.object(qs, name, value); p.start(); self.addCleanup(p.stop)
        qs.ensure_dirs()
        self.env = patch.dict(os.environ, {'HERMES_QUEUE_BRANCH':'fix/queue-isolation',
                                          'HERMES_SHARED_REPO_ROOT':str(self.base/'shared')})
        self.env.start(); self.addCleanup(self.env.stop)

    def add_record(self, name='one'):
        path = qs.COMPLETED_DIR/(name+'.json')
        path.write_text(json.dumps({'task_id': name}), encoding='utf-8')
        return path

    def test_feature_publication_does_not_touch_main(self):
        before = _run_git(['rev-parse', 'origin/main'], self.root).stdout
        self.add_record()
        self.assertTrue(qs._git_commit_and_push('test: feature'))
        self.assertEqual(_run_git(['rev-parse','origin/main'],self.root).stdout, before)
        self.assertEqual(_run_git(['rev-parse','HEAD'], self.root).stdout,
                         _run_git(['rev-parse','origin/fix/queue-isolation'],self.root).stdout)

    def test_existing_unpublished_commit_is_retried(self):
        self.add_record()
        _run_git(['add','remote-queue'],self.root)
        _run_git(['commit','-m','test: retained commit'],self.root)
        self.assertTrue(qs._git_commit_and_push('test: retry without changes'))
        self.assertEqual(_run_git(['rev-parse','HEAD'],self.root).stdout,
                         _run_git(['rev-parse','origin/fix/queue-isolation'],self.root).stdout)

    def test_wrong_configured_branch_cannot_publish(self):
        self.add_record()
        before = _run_git(['rev-parse','HEAD'],self.root).stdout
        with patch.dict(os.environ, {'HERMES_QUEUE_BRANCH':'other'}):
            self.assertFalse(qs._git_commit_and_push('must not commit'))
        self.assertEqual(_run_git(['rev-parse','HEAD'],self.root).stdout,before)

    def test_detached_head_cannot_publish(self):
        _run_git(['switch','--detach'],self.root)
        self.add_record()
        self.assertFalse(qs._git_commit_and_push('blocked'))

    def test_unrelated_staged_file_not_committed(self):
        (self.root/'owner.txt').write_text('keep staged',encoding='utf-8')
        _run_git(['add','owner.txt'],self.root)
        self.add_record()
        self.assertTrue(qs._git_commit_and_push('queue only'))
        self.assertIn('owner.txt',_run_git(['diff','--cached','--name-only'],self.root).stdout)
        self.assertNotIn('owner.txt',_run_git(['show','--pretty=','--name-only','HEAD'],self.root).stdout)

    def test_dirty_sync_preserves_file_and_stash(self):
        path=self.root/'owner.txt';path.write_text('precious',encoding='utf-8')
        before=_run_git(['stash','list'],self.root).stdout
        with patch.object(poller,'REPO_ROOT',self.root), patch.object(poller,'_git',qs._git):
            self.assertFalse(poller.git_pull_safely())
        self.assertEqual(path.read_text(),'precious')
        self.assertEqual(_run_git(['stash','list'],self.root).stdout,before)

    def test_shared_checkout_refused_even_when_clean(self):
        with patch.dict(os.environ, {'HERMES_SHARED_REPO_ROOT':str(self.root)}), patch.object(poller,'REPO_ROOT',self.root), patch.object(poller,'_git',qs._git):
            self.assertFalse(poller.git_pull_safely())

    def test_false_claim_publication_never_dispatches(self):
        task=qs.PENDING_DIR/'agent-test.json';task.write_text(json.dumps(_make_task('agent-test')),encoding='utf-8')
        with patch.object(poller,'check_kill_switch',return_value=False), patch.object(poller,'git_pull_safely',return_value=True), patch.object(poller,'find_pending_tasks',return_value=[task]), patch.object(poller,'claim_task',return_value=False), patch.object(poller,'dispatch_task') as worker:
            self.assertEqual(poller.run_poll_cycle()['status'],'claim_publication_failed')
            worker.assert_not_called()

    def test_real_claim_false_keeps_recoverable_record(self):
        task=qs.PENDING_DIR/'agent-test.json';task.write_text(json.dumps(_make_task('agent-test')),encoding='utf-8')
        with patch.object(qs,'_git_commit_and_push',return_value=False):
            self.assertFalse(qs.claim_task(task))
        self.assertTrue((qs.RUNNING_DIR/task.name).exists())

    def test_check_only_never_claims_pending(self):
        with patch.object(poller,'check_kill_switch',return_value=True), patch.object(poller,'git_pull_safely',return_value=True) as sync, patch.object(poller,'find_pending_tasks',return_value=[Path('pending.json')]), patch.object(poller,'claim_task') as claim:
            result=poller.run_poll_cycle(check_only=True)
            self.assertEqual(result['pending'],1)
            self.assertEqual(result['dispatches'],0)
            sync.assert_called_once_with(allow_publish=False);claim.assert_not_called()

    def configuration(self):
        (self.root/'remote_queue').mkdir()
        (self.root/'remote_queue/poller.py').write_text('print(123)',encoding='utf-8')
        data={'repo_root':str(self.root),'shared_repo_root':str(self.base/'shared'),
              'runtime_dir':str(self.base/'runtime'),'python_executable':sys.executable,
              'branch':'fix/queue-isolation','origin':str(self.base/'origin.git')}
        path=self.base/'config.json';path.write_text(json.dumps(data),encoding='utf-8')
        return path,data

    def test_valid_independent_configuration(self):
        path,_=self.configuration()
        self.assertEqual(cp.load_config(path)['repo_root'],self.root.resolve())

    def test_shared_configuration_rejected(self):
        path,data=self.configuration();data['shared_repo_root']=str(self.root)
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):cp.load_config(path)

    def test_runtime_inside_checkout_rejected(self):
        path,data=self.configuration();data['runtime_dir']=str(self.root/'runtime')
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):cp.load_config(path)

    def test_missing_config_never_spawns(self):
        with patch.object(cp.subprocess,'run') as spawn:
            with self.assertRaises(OSError):cp.run(self.base/'missing.json')
            spawn.assert_not_called()

    def test_worker_uses_environment_root(self):
        probe="from remote_queue.hermes_dispatch import REPO_ROOT; print(REPO_ROOT)"
        env={**os.environ,'HERMES_REPO_ROOT':str(self.root),'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,env=env,check=True)
        self.assertEqual(Path(result.stdout.strip()),self.root)

    def test_real_bootstrap_inherits_isolation_and_writes_external_status(self):
        path,data=self.configuration()
        script=self.root/'remote_queue/poller.py'
        script.write_text("import json, os\nprint(json.dumps({'status':'fixture', 'dispatches':0, 'repo_root':os.environ['HERMES_REPO_ROOT'], 'visible':os.environ['HERMES_REMOTE_VISIBLE']}))",encoding='utf-8')
        self.assertEqual(cp.run(path,check_only=True),0)
        record=json.loads((self.base/'runtime/last-check.json').read_text())
        self.assertEqual(record['result']['repo_root'],str(self.root))
        self.assertEqual(record['result']['visible'],'0')
        self.assertEqual(record['command'][-1],'--check-only')
        self.assertFalse((self.root/'last-check.json').exists())

    def test_auth_error_is_not_non_fast_forward(self):
        self.assertFalse(qs._is_non_fast_forward('remote rejected: permission denied; failed to push some refs'))

    def test_linked_worktree_configuration_refused(self):
        path,data=self.configuration()
        worktree=self.base/'linked'
        _run_git(['worktree','add','-b','linked',str(worktree)],self.root)
        data['repo_root']=str(worktree);data['branch']='linked'
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):cp.load_config(path)
