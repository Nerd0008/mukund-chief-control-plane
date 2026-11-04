import json,sys,subprocess
from pathlib import Path
from datetime import datetime,timedelta,date
import pytest
import linkedin_state as s
import linkedin_scheduled as scheduled
import linkedin_approval as approval
from linkedin_conversation import interpret
from test_linkedin_state import history,gate,personal,scheduler_fixture
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from register_linkedin_slot import register

@pytest.mark.parametrize('day',s.WEEKDAYS)
def test_custom_slot_end_to_end(tmp_path,history,day):
    db,add=history;root=tmp_path/'linkedin';root.mkdir();jobs=tmp_path/'jobs.json'
    target=date(2026,11,2)+timedelta(days=s.WEEKDAYS.index(day));body='Verified synthetic '+day+' post.'
    registry={day:'custom-job'}
    (root/'publish_slots.json').write_text(json.dumps({'schema_version':1,'weekdays':registry}))
    jobs.write_text(json.dumps({'jobs':[{'id':'custom-job','enabled':False}]}))
    (root/'publishing-policy.json').write_text('{"schema_version":1,"enabled":true}')
    add(body,role='assistant');mid=add('Approved, skip the image.')
    result=s.capture(body,target,mid,root=root,db_path=db)
    path=Path(result['artifact']);doc=s.read(path)
    doc.update(news_fact_gate=gate(body),personal_fact_gate=personal(body),requested_publish_at=f'{target}T09:30:00+00:00')
    path.write_text(json.dumps(doc))
    calls,update=scheduler_fixture(jobs)
    plan=s.plan_slot(path,target,root=root,db_path=db,jobs_path=jobs,now=datetime(2026,11,1,tzinfo=s.LONDON),updater=update)
    assert plan['planned'] and calls[-1][1]['next_run_at']==f'{target}T09:30:00+00:00'
    assert s.inspect_artifact(path,root=root,db_path=db,jobs_path=jobs)['automatic_publish_armed']
    launches=[]
    def endpoint(command,**kwargs):
        launches.append(command);ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps({'body_sha256':approval.digest(body),'result':'published'})+'\n')
        return subprocess.CompletedProcess(command,0,json.dumps({'performed':True,'post_urn':'urn:test:custom'}),'')
    early=datetime.combine(target,datetime.min.time(),s.LONDON).replace(hour=8)
    code,early_result=scheduled.run_day(day,root=root,db_path=db,jobs_path=jobs,now=early,dry_run=False,runner=endpoint)
    assert code==0 and early_result['phase']=='NOT_DUE' and not launches
    # The post-success refresh also uses the test scheduler API, never real cron.
    import unittest.mock
    with unittest.mock.patch.object(s,'_scheduler_update',lambda jid,updates,**kw:update(jid,updates)):
        code,result=scheduled.run_day(day,root=root,db_path=db,jobs_path=jobs,now=early.replace(hour=9,minute=30),dry_run=False,runner=endpoint)
    assert code==0 and result['publish_performed'] and len(launches)==1
    code,duplicate=scheduled.run_day(day,root=root,db_path=db,jobs_path=jobs,now=early.replace(hour=10),dry_run=False,runner=endpoint)
    assert code==0 and duplicate['phase']=='ALREADY_PUBLISHED' and len(launches)==1
    assert day in [x['day'] for x in s.week_status('2026-11-02',root=root,db_path=db,jobs_path=jobs)['days']]
    with pytest.raises(ValueError):s.plan_slot(path,target,root=root,db_path=db,jobs_path=jobs,updater=update)


def test_register_is_paused_and_idempotent(tmp_path):
    root=tmp_path/'linkedin';home=tmp_path/'home';jobs=tmp_path/'jobs.json'
    jobs.write_text(json.dumps({'jobs':[{'id':j,'enabled':False} for j in s.JOB_IDS.values()]}));calls=[]
    def create(**kw):
        calls.append(kw);assert kw['paused'] and kw['no_agent']
        data=s.read(jobs);data['jobs'].append({'id':'friday-test','enabled':False});jobs.write_text(json.dumps(data));return {'id':'friday-test'}
    register('friday',root=root,home=home,jobs_path=jobs,creator=create)
    register('friday',root=root,home=home,jobs_path=jobs,creator=create)
    assert len(calls)==1 and s.job_ids(root)['friday']=='friday-test'
    assert not s.job_state('friday',root=root,jobs_path=jobs)['enabled']
    assert (home/'scripts/publish_scheduled_friday.py').is_file()
    assert not (root/'drafts/schedule.json').exists()


def test_registry_rejects_bad_or_duplicate_ids(tmp_path):
    for entries in [{'friday':'same','monday':'same'},{'funday':'job'},{'friday':''}]:
        (tmp_path/'publish_slots.json').write_text(json.dumps({'schema_version':1,'weekdays':entries}))
        with pytest.raises(ValueError):s.job_ids(tmp_path)


def test_custom_day_identity_and_natural_multi_post_approval(history):
    db,add=history;body='A synthetic custom-slot post.'
    add('Thursday 2026-11-05\nA different post.\n\nFriday 2026-11-06\n'+body,role='assistant')
    assert not approval.verify_message(add('Approved'),body,db_path=db)['ok']
    assert approval.verify_message(add('Friday post approved'),body,db_path=db)['ok']
    assert interpret('Schedule Friday')['approved']
    with pytest.raises(ValueError):s.artifact_date(Path('approved_20261106_monday/linkedin_drafts.json'))
