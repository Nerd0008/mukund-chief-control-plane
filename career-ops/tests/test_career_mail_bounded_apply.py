import copy,json,hashlib,sys,re
from pathlib import Path
import pytest,openpyxl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import career_mail_bounded_apply as b
from career_mail_tracker import WorkbookTracker,digest,HEADERS


def signal(item='S01',company='Acme',role='Graduate Engineer',mid='m',**kw):
    return dict(item=item,company=company,role=role,gmail_message_id=mid,gmail_thread_id='t',category='confident existing application match',last_update_timestamp='2026-10-01T10:00:00Z',latest_status='assessment',deadline={},**kw)
def row(**kw):
    return dict(application_id='app',company='Acme',role='Graduate Engineer',region='uk',row=2,seen_message_ids=[],thread_ids=[],owner_confirmed_fields=['company','role','latest_status'],latest_status='owner status',**kw)
def report(signals):
    r={'signal_analysis':signals};r['report_id']=b.report_hash(r);return r
@pytest.fixture
def approved(monkeypatch):
    def make(signals):
        r=report(signals);monkeypatch.setattr(b,'APPROVED_REPORT',r['report_id']);return r
    return make
@pytest.fixture
def no_events(monkeypatch):monkeypatch.setattr(b,'review_events',lambda r:[])

def test_approval_binds_exact_report(approved):
    r=approved([]);b.validate_report(r);r['changed']=True
    with pytest.raises(ValueError):b.validate_report(r)
def test_owner_fields_and_status_preserved(approved,no_events):
    r=row();p=b.build_plan(approved([signal()]),[r],{})
    assert p['records'][0]['latest_status']=='owner status' and r['seen_message_ids']==[]
def test_duplicate_is_no_write(approved,no_events):
    r=row();r['seen_message_ids']=['m'];p=b.build_plan(approved([signal()]),[r],{})
    assert not p['records'] and p['duplicate_signals_avoided']==1
def test_old_message_cannot_roll_status_back():
    r=row();r['last_update_timestamp']='2026-10-07T10:00:00Z';merged,_=b.merge_signal(r,signal())
    assert merged['latest_status']=='owner status' and merged['last_update_timestamp']==r['last_update_timestamp']
def test_multiple_matches_skipped(approved,no_events):
    p=b.build_plan(approved([signal()]),[row(),dict(row(),application_id='other',row=3)],{})
    assert not p['records'] and p['skipped'][0]['candidate_count']==2
def test_unapproved_new_application_never_added(approved,no_events):
    s=signal(category_unused=None);s['category']='likely new application'
    assert not b.build_plan(approved([s]),[],{})['records']
def test_four_approved_sources_only(approved,no_events):
    signals=[signal(item,company,role,mid=item) for item,(company,role) in b.CONFIRMED.items()]
    p=b.build_plan(approved(signals),[],{i:'uk' for i in b.CONFIRMED})
    assert len(p['records'])==4 and all(r['owner_confirmed_application'] for r in p['records'])
def test_region_must_be_resolved(approved,no_events):
    c,r=b.CONFIRMED['S23']
    with pytest.raises(ValueError):b.build_plan(approved([signal('S23',c,r)]),[],{})
def test_distinct_reference_not_company_only_merge(approved,no_events):
    c,r=b.CONFIRMED['S23'];s=signal('S23',c,r,application_identity='new');old=dict(row(),company=c,role=r,application_identity='old')
    p=b.build_plan(approved([s]),[old],{'S23':'uk'})
    assert p['records'][0]['application_id']!='app'
def test_review_events_dedupe_and_do_not_include_unknown():
    signals=[]
    for company,deadline in b.REVIEW_DEADLINES.items():
        for i in range(4 if company=='National Highways' else 1):
            s=signal(company=company,mid=company+str(i));s['deadline']={'kind':'DERIVED','value':deadline,'source_message_id':'origin','reason':'received plus days','needs_review':False};signals.append(s)
    signals.append(signal('S60',company=None))
    events=b.review_events({'signal_analysis':signals})
    assert len(events)==3
    for event in events:
        assert re.fullmatch('[a-v0-9]+',event['id'])
        assert event['summary'].startswith('REVIEW — ')
        assert 'Application identity requires review. Confirm against the source Gmail message before acting.' in event['description']
        assert [r['minutes'] for r in event['reminders']['overrides']]==[1440,180]
        assert event['extendedProperties']['private']['careerOpsApplication'].startswith('review:')
    assert all('S60' not in e['description'] for e in events)
def profiles(path):
    return {'regions':{'uk':{'tracker':str(path),'sheet':'Jobs','header_row':1,'first_data_row':2,'field_map':{'company':'C','title':'D','url':'O'},'status_columns':{'application_status':'J'},'id':{'column':'A','style':'sequential','prefix':'J'},'defaults':{'application_status':'To Review'}}}}
def workbook(path):
    wb=openpyxl.Workbook();w=wb.active;w.title='Jobs';w['C1']='Company';w['D1']='Title';w['C2']='Acme';w['D2']='Graduate Engineer';w['J2']='Applied';w['K2']='owner priority';wb.save(path);wb.close()
def test_short_rows_read_without_url_column(tmp_path):
    path=tmp_path/'w.xlsx';workbook(path);records,_=WorkbookTracker(profiles(path),tmp_path/'backup').read()
    assert len(records)==1 and records[0]['canonical_owner_status']=='Applied'
def test_staging_preserves_canonical_cells(tmp_path):
    path=tmp_path/'w.xlsx';workbook(path);cfg=profiles(path);records,before=WorkbookTracker(cfg,tmp_path/'backup').read();s=signal();r,_=b.merge_signal(records[0],s)
    staged,receipt=b.stage_workbooks({'records':[r]},cfg,before,tmp_path/'stage')
    assert digest(path)==before['uk'] and receipt[0]['new'] is False and staged['uk']
def test_concurrent_change_aborts_before_calendar(tmp_path):
    path=tmp_path/'w.xlsx';workbook(path);cfg=profiles(path);before={'uk':digest(path)};path.write_bytes(path.read_bytes()+b'changed')
    class Calendar:
        def ensure(self,e):raise AssertionError('calendar must not be called')
    with pytest.raises(ValueError,match='concurrent'):b.commit_staged({'uk':b'new'},cfg,before,[{'id':'abc'}],Calendar(),tmp_path/'audit.json')
    assert path.read_bytes().endswith(b'changed')
def test_exclusive_commit_and_audit(tmp_path):
    path=tmp_path/'w.xlsx';workbook(path);cfg=profiles(path);before={'uk':digest(path)};data=path.read_bytes()
    audit=b.commit_staged({'uk':data},cfg,before,[],None,tmp_path/'audit.json')
    assert audit['state']=='applied' and audit['workbooks'][0]['after']==before['uk']


def compact_profiles(path):
    source=json.loads((Path(__file__).resolve().parents[1]/'regional_profiles.json').read_text())
    cfg=copy.deepcopy(source['regions']['uk']);cfg['tracker']=str(path)
    return {'regions':{'uk':cfg}}


def test_exact_compact_profile_resolved_without_modifying_file(tmp_path):
    p=tmp_path/'compact.xlsx';w=openpyxl.Workbook();s=w.active;s.title='Jobs';s.append(['Owner tracker']);s.append(['Date Found','Company','Role Title','Apply Link','Application Deadline','Status']);s.append(['2026-10-01','Acme','Graduate Engineer','https://example.test',None,'Applied']);w.save(p);w.close();before=digest(p)
    cfg=b.resolve_profiles(compact_profiles(p));records,_=WorkbookTracker(cfg,tmp_path/'backup').read()
    assert len(records)==1 and records[0]['company']=='Acme' and cfg['regions']['uk']['field_map']['company']=='B' and digest(p)==before


def test_unknown_layout_is_not_guessed(tmp_path):
    p=tmp_path/'bad.xlsx';w=openpyxl.Workbook();w.active.title='Jobs';w.active.append(['Unrecognized']);w.save(p);w.close()
    with pytest.raises(ValueError,match='unrecognized'):b.resolve_profiles(compact_profiles(p))


def test_new_compact_application_preserves_existing_cells(tmp_path):
    p=tmp_path/'compact.xlsx';w=openpyxl.Workbook();s=w.active;s.title='Jobs';s.append(['Owner tracker']);s.append(['Date Found','Company','Role Title','Apply Link','Application Deadline','Status']);s.append(['2026-10-01','Acme','Graduate Engineer','https://example.test',None,'Applied']);w.save(p);w.close()
    cfg=b.resolve_profiles(compact_profiles(p));before={'uk':digest(p)};c,r=b.CONFIRMED['S23'];record={'application_id':'newapp','company':c,'role':r,'region':'uk','owner_confirmed_application':True}
    staged,receipts=b.stage_workbooks({'records':[record]},cfg,before,tmp_path/'stage')
    assert receipts[0]['new'] and digest(p)==before['uk']


def test_owner_unicode_dash_location_matches_source_title():
    from career_mail_rules import role_key
    assert role_key('Graduate Security Risk Consultant - London')==role_key('Graduate Security Risk Consultant \u2014 London')


def test_reused_thread_does_not_hide_distinct_full_role():
    one=row();one['thread_ids']=['t'];two=dict(row(),application_id='other',role='Internship Analyst',row=3)
    s=signal(role='Internship Analyst')
    assert b.fresh_candidates(s,[one,two])==[two]


def test_previously_confirmed_application_preserves_new_owner_status(tmp_path):
    path=tmp_path/'w.xlsx';workbook(path);w=openpyxl.load_workbook(path);w['Jobs']['J2']='Rejected';w.save(path);w.close();cfg=profiles(path);records,before=WorkbookTracker(cfg,tmp_path/'backup').read()
    r,_=b.merge_signal(records[0],signal());r['owner_confirmed_application']=True
    staged,_=b.stage_workbooks({'records':[r]},cfg,before,tmp_path/'stage')
    w=openpyxl.load_workbook(tmp_path/'stage'/'uk.xlsx');assert w['Jobs']['J2'].value=='Rejected';w.close()
