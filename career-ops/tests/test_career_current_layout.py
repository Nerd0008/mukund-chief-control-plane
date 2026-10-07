"""Current-layout scheduled-path invariants, isolated workbooks only."""
import copy, json, sys
from pathlib import Path
import pytest, openpyxl
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from career_tracker_layout import resolve_profiles
from career_mail_tracker import WorkbookTracker, digest
from career_mail_monitor import run_scan, report_hash, schedule_plan
from tracker_writer import Tracker
from career_google_clients import GmailReader
from career_google_auth import GoogleError

def profiles(path):
    cfg=json.loads((Path(__file__).resolve().parents[1]/'regional_profiles.json').read_text())
    uk=copy.deepcopy(cfg['regions']['uk']);uk['tracker']=str(path)
    return {'regions':{'uk':uk}}

def workbook(path):
    cfg=profiles(path)['regions']['uk'];wb=openpyxl.Workbook();ws=wb.active;ws.title=cfg['sheet']
    for col, header in cfg['required_headers'].items():ws[f'{col}2']=header
    ws['B3']='Owner Company';ws['C3']='Owner Role';ws['F3']='Applied'
    wb.save(path);wb.close()

def test_url_less_owner_row_occupies_append_position(tmp_path):
    p=tmp_path/'tracker.xlsx';workbook(p);cfg=profiles(p);before=digest(p)
    tr=Tracker(p,cfg['regions']['uk']);assert tr.last_data_row()==3;tr.wb.close()
    tracker=WorkbookTracker(cfg,tmp_path/'backup');rows,_=tracker.read();assert len(rows)==1
    tracker.upsert(dict(application_id='new',company='Other Company',role='Other Role',region='uk'))
    wb=openpyxl.load_workbook(p);ws=wb['Jobs'];assert ws['F3'].value=='Applied';assert ws['B4'].value=='Other Company';assert ws['G2'].value=='Career Ops Job ID';assert ws['G4'].value=='UK-MAIL-new';assert ws['H2'].value.startswith('Career Ops Email');wb.close()

def test_stale_layout_rejected_by_mail_and_general_tracker(tmp_path):
    p=tmp_path/'tracker.xlsx';workbook(p);wb=openpyxl.load_workbook(p);wb['Jobs']['B2']='Stale';wb.save(p);wb.close();cfg=profiles(p)
    with pytest.raises(ValueError):WorkbookTracker(cfg,tmp_path/'b')
    with pytest.raises(ValueError):Tracker(p,cfg['regions']['uk'])

def test_schedule_stays_disabled_and_dry_run():
    plan=schedule_plan({'scan_interval_minutes':60});assert not plan['install_enabled'];assert '--apply' not in plan['arguments']

def test_verified_baseline_uses_history_without_acknowledging_review(tmp_path):
    p=tmp_path/'tracker.xlsx';workbook(p);tracker=WorkbookTracker(profiles(p),tmp_path/'b');baseline={'checkpoint_proposed':'100','processed_ids':['unresolved']};baseline['report_id']=report_hash(baseline);bp=tmp_path/'baseline.json';bp.write_text(json.dumps(baseline));calls=[]
    class Reader:
        def read_window(self, checkpoint, **kwargs):calls.append(checkpoint);return {'messages':[], 'checkpoint':'101','mode':'incremental'}
    before=digest(p);result=run_scan({'backfill_days':30,'max_messages':10},tmp_path/'runtime',reader=Reader(),tracker=tracker,baseline_report=bp)
    assert calls==['100'];assert result['tracker_writes']==result['calendar_writes']==0;assert result['processed_ids']==[];assert digest(p)==before;assert not (tmp_path/'runtime/checkpoint.json').exists()

def test_invalid_baseline_rejected_without_mailbox_call(tmp_path):
    bp=tmp_path/'baseline.json';bp.write_text('{"report_id":"bad","checkpoint_proposed":"100"}')
    with pytest.raises(ValueError):run_scan({},tmp_path/'runtime',baseline_report=bp)

def test_expired_history_falls_back_to_bounded_get_only_backfill():
    calls=[]
    def transport(method,url,**kwargs):
        calls.append((method,url))
        if '/profile' in url:return {'historyId':'200'}
        if '/history' in url:raise GoogleError('expired',status=404)
        if '/messages?' in url:return {'messages':[]}
        raise AssertionError(url)
    result=GmailReader('fake',transport,request_interval=0).read_window('100',days=30,max_messages=10)
    assert result['mode']=='expired_history_backfill';assert result['gmail_mutations']==0;assert all(m=='GET' for m,u in calls);assert 'after%3A' in calls[-1][1]

def test_html_image_boolean_alt_does_not_abort_scan():
    from career_mail_rules import visible
    assert 'application' in visible('<div>Your application<img alt></div>')

def accepted_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    p=tmp_path/'tracker.xlsx';workbook(p);cfg=profiles(p)
    tracker=WorkbookTracker(cfg,tmp_path/'b');records,_=tracker.read();record=records[0]
    record.update(seen_message_ids=['accepted-message'],thread_ids=['accepted-thread'],latest_status='assessment')
    tracker.upsert(record)
    root=tmp_path/'accepted';(root/'staged').mkdir(parents=True)
    snapshot=root/'staged/uk.xlsx';snapshot.write_bytes(p.read_bytes())
    (root/'result.json').write_text(json.dumps({'status':'PASS','after_hashes':{'uk':digest(snapshot)}}))
    (root/'apply-audit.json').write_text('{"state":"applied"}')
    workbook(p)  # simulate the external six-column workbook replacement
    cfg['accepted_mail_state']='accepted'
    return p,cfg,snapshot

def test_accepted_snapshot_recovers_dedupe_without_restoring_workbook(tmp_path,monkeypatch):
    p,cfg,snapshot=accepted_fixture(tmp_path,monkeypatch);before=digest(p)
    tracker=WorkbookTracker(cfg,tmp_path/'b');records,_=tracker.read()
    assert records[0]['seen_message_ids']==['accepted-message'];assert digest(p)==before
    assert records[0]['row']==3 and records[0]['canonical_owner_status']=='Applied'
    assert tracker.accepted_state_recovered_records==1

def test_accepted_snapshot_tampering_aborts(tmp_path,monkeypatch):
    p,cfg,snapshot=accepted_fixture(tmp_path,monkeypatch);snapshot.write_bytes(snapshot.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='fingerprint'):WorkbookTracker(cfg,tmp_path/'b').read()

def test_ambiguous_snapshot_identity_is_never_fuzzily_merged(tmp_path,monkeypatch):
    p,cfg,snapshot=accepted_fixture(tmp_path,monkeypatch);wb=openpyxl.load_workbook(p);ws=wb['Jobs'];ws['B4']='Owner Company';ws['C4']='Owner Role';wb.save(p);wb.close()
    with pytest.raises(ValueError,match='reconciliation'):WorkbookTracker(cfg,tmp_path/'b').read()

def test_rollover_clears_hyperlinks_before_reusing_plain_range_rows(tmp_path):
    from tracker_rollover import _clear_block
    p=tmp_path/'tracker.xlsx';workbook(p);wb=openpyxl.load_workbook(p);ws=wb['Jobs'];ws['D3']='https://example.test';ws['D3'].hyperlink='https://example.test';_clear_block(ws,3,3,6);wb.save(p);wb.close()
    wb=openpyxl.load_workbook(p);assert wb['Jobs']['D3'].value is None and wb['Jobs']['D3'].hyperlink is None;wb.close()
