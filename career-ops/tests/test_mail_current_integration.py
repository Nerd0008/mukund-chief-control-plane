"""Current-layout mail integration: private workbooks and private sidecars only."""
import json
from pathlib import Path
import pytest, openpyxl
import career_mail_bounded_apply as bounded
from career_mail_tracker import WorkbookTracker,digest
from career_mail_monitor import apply_report
from test_career_current_layout import workbook,profiles

@pytest.fixture
def current(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    path=tmp_path/'tracker.xlsx';workbook(path);cfg=profiles(path)
    return path,cfg,WorkbookTracker(cfg,tmp_path/'backups')

def new_record():
    return dict(application_id='owner-approved-application',company='Verified Employer',
        role='Graduate Cyber Engineer',region='uk',owner_confirmed_application=True,
        confidence='high',needs_review=False,seen_message_ids=['synthetic-message'])

def test_new_confirmed_mail_uses_canonical_writer_and_replay_dedupes(current,tmp_path):
    path,cfg,tracker=current;record=new_record()
    report={'proposed_records':[record],'proposed_calendar_events':[]}
    apply_report(report,tracker,None,tmp_path/'audit.json')
    after=digest(path);rows,_=tracker.read()
    assert len(rows)==2 and rows[-1]['seen_message_ids']==['synthetic-message']
    apply_report(report,tracker,None,tmp_path/'audit.json')
    assert digest(path)==after and len(tracker.read()[0])==2
    w=openpyxl.load_workbook(path);s=w['Jobs']
    assert s.max_column==6 and s['F3'].value=='Applied' and s['F4'].value=='Applied'
    w.close()

@pytest.mark.parametrize('reason',['not_approved','needs_review','stale_row'])
def test_new_untrusted_mail_never_creates_a_row(current,reason):
    path,cfg,tracker=current;before=digest(path);record=new_record()
    if reason=='not_approved':record['owner_confirmed_application']=False
    elif reason=='needs_review':record['needs_review']=True
    else:record['row']=900
    with pytest.raises(ValueError):tracker.upsert(record)
    assert digest(path)==before

def test_owner_deleted_application_is_not_resurrected(current):
    path,cfg,tracker=current;record=new_record();tracker.upsert(record)
    w=openpyxl.load_workbook(path);w['Jobs'].delete_rows(4);w.save(path);w.close()
    record.pop('row');before=digest(path)
    with pytest.raises(ValueError,match='owner-deleted'):tracker.upsert(record)
    assert digest(path)==before

def test_changed_posting_cannot_inherit_metadata(current):
    path,cfg,tracker=current;record=tracker.read()[0][0]
    record['canonical_job_path']='/different-requisition'
    with pytest.raises(ValueError,match='conflicting mailbox posting'):tracker.upsert(record)

def test_staging_isolates_live_metadata_then_commits_under_shared_lock(current,tmp_path):
    path,cfg,tracker=current;before={'uk':digest(path)};record=new_record()
    store=Path(__import__('os').environ['LOCALAPPDATA'])/cfg['regions']['uk']['mail_metadata_sidecar']
    staged,receipts=bounded.stage_workbooks({'records':[record]},cfg,before,tmp_path/'stage')
    assert digest(path)==before['uk'] and not store.exists()
    assert staged.metadata and receipts[0]['new']
    bounded.commit_staged(staged,cfg,before,[],None,tmp_path/'commit-audit.json')
    assert store.exists() and len(tracker.read()[0])==2
    assert tracker.read()[0][-1]['seen_message_ids']==['synthetic-message']

def test_sidecar_drift_aborts_before_any_workbook_commit(current,tmp_path):
    path,cfg,tracker=current;before={'uk':digest(path)}
    staged,_=bounded.stage_workbooks({'records':[new_record()]},cfg,before,tmp_path/'stage')
    store=Path(staged.metadata[0]['path']);store.parent.mkdir(parents=True,exist_ok=True)
    store.write_text('{"records":{}}',encoding='utf-8')
    with pytest.raises(ValueError,match='concurrent metadata'):
        bounded.commit_staged(staged,cfg,before,[],None,tmp_path/'commit-audit.json')
    assert digest(path)==before['uk']

def test_staged_commit_refuses_an_overlapping_writer(current,tmp_path):
    path,cfg,tracker=current;before={'uk':digest(path)}
    staged,_=bounded.stage_workbooks({'records':[new_record()]},cfg,before,tmp_path/'stage')
    lock=path.with_suffix('.xlsx.career-mail.lock');lock.write_text('active',encoding='utf-8')
    with pytest.raises(FileExistsError):bounded.commit_staged(staged,cfg,before,[],None,tmp_path/'audit.json')
    assert digest(path)==before['uk'] and lock.read_text()=='active'

def test_mail_company_text_cannot_become_an_excel_formula(current):
    path,cfg,tracker=current;record=new_record();record['company']='=1+1'
    tracker.upsert(record)
    book=openpyxl.load_workbook(path);cell=book['Jobs']['B4']
    assert cell.value=='=1+1' and cell.data_type=='s'
    book.close()


def test_partial_metadata_failure_replay_does_not_append_again(current,monkeypatch):
    import career_mail_tracker as module
    path,cfg,tracker=current;record=new_record();real_replace=module.os.replace
    def fail_sidecar(source,target):
        if str(target).endswith('uk-application-state.json'):
            raise OSError('synthetic interrupted metadata commit')
        return real_replace(source,target)
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'replace',fail_sidecar)
        with pytest.raises(OSError):tracker.upsert(record)
    assert len(tracker.read()[0])==2  # row committed; checkpoint caller must not advance
    tracker.upsert(record)
    assert len(tracker.read()[0])==2 and tracker.read()[0][-1]['seen_message_ids']==['synthetic-message']


def test_ambiguous_exact_company_role_stays_blocked(current):
    path,cfg,tracker=current
    book=openpyxl.load_workbook(path);sheet=book['Jobs']
    for row in (4,5):
        sheet[f'B{row}']='Verified Employer';sheet[f'C{row}']='Graduate Cyber Engineer'
    book.save(path);book.close();before=digest(path)
    with pytest.raises(ValueError,match='ambiguous mailbox application'):tracker.upsert(new_record())
    assert digest(path)==before


def test_new_conflicting_posting_evidence_is_rejected_before_row_write(current):
    path,cfg,tracker=current;record=new_record();record['canonical_job_host']='unknown.example'
    before=digest(path)
    with pytest.raises(ValueError,match='before insertion'):tracker.upsert(record)
    assert digest(path)==before


def test_normal_sidecar_write_does_not_overwrite_concurrent_metadata(current,monkeypatch):
    import career_mail_tracker as module
    path,cfg,tracker=current;record=tracker.read()[0][0];tracker.upsert(record)
    store=Path(__import__('os').environ['LOCALAPPDATA'])/cfg['regions']['uk']['mail_metadata_sidecar']
    real_dumps=module.json.dumps;changed=False
    def concurrent(value,*args,**kwargs):
        nonlocal changed
        if not changed and isinstance(value,dict) and 'records' in value:
            changed=True
            store.write_text(real_dumps({'records':{},'revision':'external'}),encoding='utf-8')
        return real_dumps(value,*args,**kwargs)
    monkeypatch.setattr(module.json,'dumps',concurrent)
    with pytest.raises(ValueError,match='metadata changed concurrently'):tracker.upsert(record)
    assert json.loads(store.read_text(encoding='utf-8'))['revision']=='external'
