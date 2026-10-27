import json,inspect
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import hermes_linkedin_control as control
import linkedin_state as s
from test_linkedin_state import artifact,history,scheduler_fixture


def test_resume_unapproved_or_empty_cannot_enable_jobs(tmp_path,history):
    root,path,db,jobs,mid=artifact(tmp_path,history)
    calls,update=scheduler_fixture(jobs)
    result=control.manage('tuesday','resume',root=root,db_path=db,jobs_path=jobs,
        now=datetime(2026,10,26,12,tzinfo=s.LONDON),updater=update)
    assert not result['success'] and result['phase']=='NOT_ARMED' and not calls


def test_resume_approved_future_uses_pinned_time_not_stale_due(tmp_path,history):
    root,path,db,jobs,mid=artifact(tmp_path,history)
    (root/'publishing-policy.json').write_text(json.dumps({'schema_version':1,'enabled':True}))
    calls,update=scheduler_fixture(jobs)
    s.plan_slot(path,'2026-10-27',root=root,db_path=db,jobs_path=jobs,dry_run=True)
    # Write the manifest with the production state method, using only the fixture API.
    s.plan_slot(path,'2026-10-27',root=root,db_path=db,jobs_path=jobs,
        now=datetime(2026,10,26,12,tzinfo=s.LONDON),updater=update)
    result=control.manage('tuesday','resume',root=root,db_path=db,jobs_path=jobs,
        now=datetime(2026,10,26,13,tzinfo=s.LONDON),updater=update)
    assert result['success'] and s.job_state('tuesday',jobs_path=jobs)['next_run_at']=='2026-10-27T08:00:00+00:00'
    assert not result['publish_performed']


def test_wrong_day_run_never_dispatches(tmp_path):
    result=control.manage('wednesday','run',root=tmp_path,now=datetime(2026,10,27,19,tzinfo=s.LONDON))
    assert result['phase']=='NOT_DUE' and result['network_calls']==0


def test_generic_cron_guard_is_narrow_and_preserves_unrelated_tools(monkeypatch):
    calls=[]
    def original(action,job_id=None,**kwargs):calls.append((action,job_id));return 'ORIGINAL'
    module=NS(cronjob=original)
    monkeypatch.setattr(control,'protected_day',lambda ref:'tuesday' if ref=='protected' else None)
    monkeypatch.setattr(control,'manage',lambda *a:{'success':False,'phase':'NOT_ARMED'})
    control.install(module)
    assert json.loads(module.cronjob('resume','protected'))['phase']=='NOT_ARMED'
    assert module.cronjob('resume','other')=='ORIGINAL'
    assert module.cronjob('pause','protected')=='ORIGINAL'
    assert module.cronjob('list')=='ORIGINAL'
    assert calls==[('resume','other'),('pause','protected'),('list',None)]


def test_guard_failure_never_falls_through_to_mutation(monkeypatch):
    def original(action,job_id=None):pytest.fail('unsafe generic mutation dispatched')
    module=NS(cronjob=original)
    monkeypatch.setattr(control,'protected_day',lambda ref:'tuesday')
    monkeypatch.setattr(control,'manage',lambda *a:(_ for _ in ()).throw(OSError('unavailable')))
    control.install(module)
    assert json.loads(module.cronjob('resume','protected'))['phase']=='CONTROL_UNAVAILABLE'
