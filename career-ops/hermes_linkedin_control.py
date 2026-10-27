"""Readiness-aware control of the three existing LinkedIn publisher jobs only.

Generic cron remains available for other jobs. This boundary never creates owner
consent, changes a post, calls a model or invokes the publisher itself.
"""
from __future__ import annotations
import functools,inspect,json
from datetime import datetime
import linkedin_state as state


def protected_day(reference,*,resolver=None):
    for day,job_id in state.JOB_IDS.items():
        if reference==job_id:return day
    if not reference:return None
    if resolver is None:
        from cron.jobs import resolve_job_ref
        resolver=resolve_job_ref
    job=resolver(reference)
    if job:
        return next((day for day,jid in state.JOB_IDS.items() if jid==job.get('id')),None)
    return None


def manage(day,action,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,now=None,updater=None):
    now=now or datetime.now(state.LONDON)
    if action=='resume':
        with state.locked(root):
            result=state.refresh_publishing_jobs(root=root,jobs_path=jobs_path,db_path=db_path,now=now,updater=updater,days=[day])
        armed=any(row['day']==day for row in result['armed'])
        return {'success':armed,'phase':'SCHEDULED' if armed else 'NOT_ARMED',
            'reason_code':'approved_future_slot_armed' if armed else 'no_approved_verified_future_slot',
            'message':'Protected LinkedIn jobs use exact approved future slots; no stale occurrence was resumed.',
            **result,'job':state.job_state(day,jobs_path=jobs_path),'publish_performed':False,'network_calls':0}
    if action in ('run','run_now','trigger'):
        if now.strftime('%A').lower()!=day:
            return {'success':True,'phase':'NOT_DUE','outcome':'NO_ACTION','publish_performed':False,'network_calls':0}
        slots=state.load_slots(root/'drafts/schedule.json');slot=slots.get(now.date().isoformat())
        if not slot:return {'success':False,'phase':'NOT_ARMED','reason_code':'no_approved_exact_slot','publish_performed':False,'network_calls':0}
        status=state.inspect_artifact(state.absolute(slot['draft_path']),root=root,db_path=db_path,jobs_path=jobs_path)
        if status['published']:
            return {'success':True,'phase':'ALREADY_PUBLISHED','outcome':'NO_ACTION','publish_performed':False,'network_calls':0}
        when=datetime.fromisoformat(slot['publish_at'])
        if now<when:return {'success':True,'phase':'NOT_DUE','outcome':'NO_ACTION','publish_performed':False,'network_calls':0}
        if status['automatic_publish_armed']:return None  # Existing cron executes with independent publisher guards.
        return {'success':False,'phase':status['phase'],'reason_code':'canonical_readiness_required',
            'canonical_status':status,'publish_performed':False,'network_calls':0}
    return {'success':False,'phase':'PROTECTED_WORKFLOW','reason_code':'use_canonical_linkedin_state',
        'message':'Use linkedin_state capture/reconcile/plan or publishing enable/disable; generic cron cannot rewrite protected publishing payloads.',
        'publish_performed':False,'network_calls':0}


def install(module=None):
    if module is None:
        from tools import cronjob_tools as module
    if getattr(module.cronjob,'_linkedin_control_installed',False):return
    original=module.cronjob;signature=inspect.signature(original)
    @functools.wraps(original)
    def guarded(*args,**kwargs):
        bound=signature.bind_partial(*args,**kwargs);values=bound.arguments
        action=str(values.get('action','')).lower()
        if action in ('list','pause'):return original(*args,**kwargs)
        day=protected_day(values.get('job_id'))
        if day is None:return original(*args,**kwargs)
        try:result=manage(day,action)
        except Exception as exc:
            result={'success':False,'phase':'CONTROL_UNAVAILABLE','error_type':type(exc).__name__,
                'reason_code':'canonical_state_unavailable','publish_performed':False,'network_calls':0}
        if result is not None:return json.dumps(result,ensure_ascii=False)
        return original(*args,**kwargs)
    guarded._linkedin_control_installed=True
    module.cronjob=guarded
