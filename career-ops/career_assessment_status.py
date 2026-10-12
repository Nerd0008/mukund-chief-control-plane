"""Read-only assessment lifecycle audit, independent of ingestion checkpoints."""
import datetime as dt,json,re
from career_mail_parser import mail_fields,extract_deadline
from career_mail_matching import resolve
from career_mail_monitor import prepare_messages,time_key
QUERY='{assessment interview hirevue talogy shl cappfinity testgorilla codility hackerrank}'

def newsletter(mail):
    # Marketing assessment articles/links are not personal invitations.
    subject=mail.get('subject','');body=mail.get('body','')
    if re.search(r'(?i)newsletter|job alerts?|jobs for you|recommended jobs|jobs you may|latest jobs',subject):return True
    return bool(re.search(r'(?i)unsubscribe|manage (?:your )?(?:email )?preferences',body) and
                re.search(r'(?i)totaljobs|job alerts?|recommended jobs|newsletter',subject+' '+str(mail.get('from',''))) and
                not re.search(r'(?i)(?:your application|you are invited|invitation to complete|please complete your assessment)',body))

def lifecycle(signal,mail,now):
    text=mail.get('subject','')+'\n'+mail.get('body','')
    if signal.get('latest_status')=='assessment_completed' or re.search(r'(?i)(?:you have|you.ve|you successfully) (?:completed|submitted) (?:your |the )?(?:assessment|test|interview)|thank you for (?:completing|taking) (?:your |the )?(?:assessment|test|interview)',text):
        return 'COMPLETED','explicit completion/submission confirmation'
    if re.search(r'(?i)(?:your |the )?(?:assessment|test|interview|invitation|assessment link) (?:has |is |was )?(?:expired|closed)|deadline (?:has )?passed',text):
        return 'EXPIRED','explicit expiry/closure notice'
    deadline=signal.get('deadline') or {}
    value=deadline.get('value')
    if value and not deadline.get('needs_review'):
        try:
            if deadline.get('date_only'):
                date=dt.date.fromisoformat(value)
                if date<now.date():return 'EXPIRED','explicit deadline date is past'
                if date>now.date():return 'OPEN','explicit deadline date is future; portal availability not confirmed'
                return 'UNKNOWN','date-only deadline is today; cutoff/timezone not established'
            stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            if stamp.tzinfo is None:raise ValueError()
            return ('EXPIRED','reliable deadline has passed') if stamp<=now else ('OPEN','reliable future deadline; portal availability not confirmed')
        except ValueError:pass
    return 'UNKNOWN','no reliable deadline or completion/closure evidence; an invitation or link alone does not prove it is still open'

def analyze(messages,records,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    rows={};ignored=0
    for raw in sorted(prepare_messages(messages,records),key=lambda r:int(r.get('internalDate',0)) if 'payload' in r else time_key(r.get('received_at'))):
        mail=mail_fields(raw)
        if newsletter(mail):ignored+=1;continue
        signal,matches,method=resolve(raw,records)
        if signal is None or not signal.get('assessment_type'):ignored+=1;continue
        company,role=signal.get('company'),signal.get('role')
        if len(matches)==1:
            company,role=matches[0]['company'],matches[0]['role']
        status,reason=lifecycle(signal,mail,now)
        key=(signal.get('gmail_thread_id'),signal.get('application_identity'),signal.get('assessment_type'))
        # Completion and expiry updates supersede invitations in the same thread.
        kind=signal.get('assessment_type','')
        key=(key[0],key[1],'interview' if 'interview' in kind else 'assessment')
        rows[key]={'company':company,'role':role,'status':status,'reason':reason,
                   'received_at':signal.get('assessment_received_date'),'deadline':(signal.get('deadline') or {}).get('value'),
                   'deadline_type':(signal.get('deadline') or {}).get('kind'),'identity_needs_review':len(matches)!=1 and (not company or not role or len(matches)>1),
                   'source_message_id':signal['gmail_message_id'],'source_thread_id':signal['gmail_thread_id'],
                   'portal_checked':False}
    output=list(rows.values())
    return {'assessments':output,'counts':{s:sum(r['status']==s for r in output) for s in ('OPEN','EXPIRED','COMPLETED','UNKNOWN')},
            'messages_inspected':len(messages),'ignored_non_assessment':ignored,'gmail_mutations':0,'tracker_writes':0,'calendar_writes':0,
            'checkpoint_advanced':False,'model_calls':0,
            'instruction':'Answer only assessment status. UNKNOWN is not OPEN. Do not recommend acting on unknown links. Do not request employer confirmation to report status. No unrelated CV/tracker tasks. No portal interaction or test submission.'}

def main():
    from career_google_auth import access_token,GoogleError
    from career_google_clients import GmailReader
    from career_mail_monitor import CONFIG,REPO,RUNTIME,read_json
    from career_mail_tracker import WorkbookTracker
    try:
        config=read_json(CONFIG,{})
        records,_=WorkbookTracker(read_json(REPO/config['regional_profiles'],{}),RUNTIME/'backups').read()
        window=GmailReader(access_token).read_window(None,days=30,max_messages=200,query=QUERY)
        result=analyze(window['messages'],records)
        result['unavailable_messages']=window.get('unavailable_messages',0)
        print(json.dumps(result))
    except Exception:
        # Never serialize HTTP URLs, tokens, email body, or private exception text.
        print(json.dumps({'ok':False,'error':'assessment audit could not complete; no status conclusions or writes made'}))
        raise SystemExit(1)
if __name__=='__main__':main()
