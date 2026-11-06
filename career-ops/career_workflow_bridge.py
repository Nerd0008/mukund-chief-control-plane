"""Bounded existing Career Ops workflows; no invented facts, SDK paths or consent."""
from __future__ import annotations
import hashlib,json,re,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,date
import linkedin_state as state


def intent(text,workflow):
    text=str(text).strip()
    if workflow=='career_search':
        if re.search(r'(?i)^(?:please |can you )?(?:fix|repair|investigate|debug|explain|write|build|create|stop|pause|disable)\b',text):return 'INVESTIGATE'
        if re.search(r'(?i)\b(?:report|status|results|last scan|what.*found|where.*jobs)\b',text):return 'SEARCH_REPORT'
        if re.search(r'(?i)^(?:please |can you )?(?:run|start|resume|find|search for)\b',text):return 'RUN_SEARCH'
        return 'QUERY'
    if workflow!='linkedin':return None
    from linkedin_conversation import interpret
    if not re.search(r'(?i)^(?:please |can you )?(?:investigate|debug|fix|repair)\b',text):
        spoken=interpret(text)
        if spoken['approved'] or spoken['skip_image'] or spoken['publish_at']:
            return 'PUBLISH_NOW' if spoken['publish_now'] else 'APPROVAL'
    if re.match(r'(?i)^(?:approved[,!. ]+)?(?:(?:please|can you|could you) )?(?:publish|post)\b.*\bnow\b',text):return 'PUBLISH_NOW'
    if re.match(r'(?i)^approve(?:d)?\b',text) or (re.match(r'(?i)^(?:perfect|yes|schedule)\b',text) and re.search(r'(?i)\bapproved\b',text)):return 'APPROVAL'
    if re.search(r'(?i)^(?:please |can you )?(?:investigate|debug|fix|repair)\b',text):return 'INVESTIGATE'
    if re.search(r'(?i)\bbuild\b.*(?:artefact|artifact)',text):return 'BUILD_ARTIFACTS'
    if re.search(r'(?i)\b(?:show|see|give|remaining|rest of)\b.*(?:posts?|drafts?|remaining|week)|show me (?:them|the remaining ones)',text):return 'SHOW_DRAFTS'
    if re.search(r'(?i)\b(?:generate|create|make)\b.*\bimages?\b',text):return 'IMAGE'
    if re.search(r'(?i)\b(?:draft|write|prepare|generate|create)\b.*\bposts?\b',text):return 'PREPARE'
    return 'STATUS'


def show(*,week_of=None,root=state.ROOT,jobs_path=state.JOBS,db_path=None):
    monday=week_of or (datetime.now(state.LONDON).date()-timedelta(days=datetime.now(state.LONDON).weekday())).isoformat()
    result=state.week_status(monday,root=root,jobs_path=jobs_path,db_path=db_path)
    return {'ok':True,'week_of':monday,'days':result['days'],'publish_performed':False,'network_calls':0,'writes':0}


def render_drafts(doc):
    lines=['Existing LinkedIn drafts — '+doc['week_of']]
    for row in doc['days']:
        if row.get('published'):
            lines.append(row['day'].title()+': already published; it will not be posted again.');continue
        labels={'AWAITING_OWNER_APPROVAL':'Ready for your review','DRAFT_BLOCKED':'Factual checks need attention','APPROVED_BUT_BLOCKED':'Approved; checks need attention','SCHEDULED':'Scheduled','NO_ARTIFACT':'No draft yet','APPROVED_READY_PAUSED':'Approved and ready','APPROVED_READY_UNSCHEDULED':'Approved; waiting for a time'}
        lines+=['',row['day'].title()+' '+row['date']+' — '+labels.get(row['phase'],'Draft status available')]
        if row.get('draft_exists'):
            lines += [row['post_text']]
            if row.get('reviews_ready') and not row.get('owner_approved'):lines+=['You can approve this in your own words, and tell me when to post or whether to skip the image.']
            elif not row.get('reviews_ready'):lines+=['You can approve the text now. Publication will wait for the factual checks.']
            elif row.get('owner_approved') and not row.get('content_ready'):lines+=['Your approval is preserved. Required image or integrity checks are incomplete; do not approve the unchanged text again.']
            if row.get('alternatives'):lines+=['Another version is preserved separately; it has not silently replaced this selected draft.']
        else:lines+=['No dated draft is available.']
    lines+=['','No image was generated, approval granted or post published by this retrieval.']
    return '\n\n'.join(lines)


def _selected(day,sha,post_id=None,**options):
    if post_id and day is None:
        if not re.fullmatch(r'[0-9a-f]{32}',post_id):raise ValueError('invalid post ID')
        root=Path(options.get('root',state.ROOT));jobs=options.get('jobs_path',state.JOBS);db=options.get('db_path')
        found=[]
        for path in (root/'drafts').glob('approved_*/linkedin_drafts.json'):
            try:
                doc=state.read(path)
                if doc.get('post_id')!=post_id:continue
                status=state.inspect_artifact(path,root=root,jobs_path=jobs,db_path=db)
                if not status['artifact_identity_valid']:raise ValueError('post artifact identity invalid')
                target=status['target_date']
                found.append({**status,'day':date.fromisoformat(target).strftime('%A').lower(),'date':target,
                              'source_kind':'DATED_ARTIFACT','post_text':state.body_of(doc),'draft_exists':True})
            except (OSError,TypeError):continue
        if len(found)>1:raise ValueError('post ID is duplicated across artifacts')
        if not found:
            for path in (root/'review').glob('*/weekly.json'):
                try:doc=state.read(path)
                except (OSError,ValueError):continue
                for entry in (doc.get('posts') or {}).values():
                    if not isinstance(entry,dict) or entry.get('post_id')!=post_id or not entry.get('target_date'):continue
                    target=date.fromisoformat(entry['target_date'])
                    prepared=state.prepared_status(target,root=root,jobs_path=jobs)
                    if prepared and prepared.get('post_id')==post_id:
                        found.append({**prepared,'day':target.strftime('%A').lower(),'date':target.isoformat(),
                                      'source_kind':'REVIEWED_PREPARED' if prepared.get('reviews_ready') else 'PREPARED','draft_exists':True})
        if len(found)!=1:raise ValueError('post ID does not uniquely identify a post')
        row=found[0]
        if sha and sha!=row['body_sha256']:raise ValueError('version mismatch: retrieve and approve the exact selected draft first')
        return row
    if day not in state.WEEKDAYS:raise ValueError('invalid publishing weekday')
    row=next((r for r in show(**options)['days'] if r['day']==day),None)
    if row is None:raise ValueError('no dated draft')
    if not post_id and sha and row.get('body_sha256')!=sha:
        candidates=[v for v in row.get('alternatives',[]) if v.get('body_sha256')==sha]
        if len(candidates)==1 and candidates[0].get('post_id'):post_id=candidates[0]['post_id']
    if post_id and row.get('post_id')!=post_id:
        matches=[v for v in row.get('alternatives',[]) if v.get('post_id')==post_id]
        if len(matches)!=1:raise ValueError('post ID does not uniquely identify a draft for this day')
        alt=matches[0];path=Path(alt['artifact'])
        if alt.get('source_kind') in ('PREPARED','REVIEWED_PREPARED'):
            prepared=state.prepared_status(date.fromisoformat(row['date']),root=options.get('root',state.ROOT),jobs_path=options.get('jobs_path',state.JOBS))
            row={**prepared,'day':day,'date':row['date'],'source_kind':alt['source_kind'],'draft_exists':True}
        else:
            status=state.inspect_artifact(path,root=options.get('root',state.ROOT),jobs_path=options.get('jobs_path',state.JOBS),db_path=options.get('db_path'))
            row={**status,'day':day,'date':row['date'],'source_kind':'DATED_ARTIFACT','post_text':state.body_of(state.read(path)),'draft_exists':True}
    if not row.get('draft_exists'):raise ValueError('no dated draft')
    if post_id and row.get('post_id')!=post_id:raise ValueError('post ID mismatch')
    if sha and sha!=row['body_sha256']:raise ValueError('version mismatch: retrieve and approve the exact selected draft first')
    if not sha and not post_id:raise ValueError('post ID or exact body hash required')
    return row


def image(row,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,generator=None):
    path=Path(row.get('captured_artifact') or (row.get('artifact') if row.get('source_kind')=='DATED_ARTIFACT' else None) or (Path(root)/'drafts'/f"approved_{date.fromisoformat(row['date']):%Y%m%d}_{row['day']}"/'linkedin_drafts.json'))
    current=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
    if current['published']:return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False}
    if not current['owner_approved'] or not current['reviews_ready']:raise ValueError('exact owner approval and passing reviews required before image generation')
    if current['body_sha256']!=row['body_sha256']:raise ValueError('image version mismatch')
    doc=state.read(path);before=state.file_hash(path);sha=current['body_sha256']
    asset=Path(doc['image_path']) if doc.get('image_path') else None
    if doc.get('image_body_sha256')==sha and asset and asset.is_file():return {'ok':True,'phase':'IMAGE_READY','image':str(asset),'reused':True}
    if generator is None:
        if Path(root).resolve()!=state.ROOT.resolve():raise ValueError('private fixture requires an injected image generator')
        import sys
        source=state.REPO/'exec-brain'
        if str(source) not in sys.path:sys.path.insert(0,str(source))
        import linkedin_content_gen as gen
        generator=lambda body:gen.generate_image_bytes(gen.build_image_prompt(body))
    data=generator(state.body_of(doc))
    if not data:raise ValueError('image generator returned no image')
    suffix='.png' if data.startswith(b'\x89PNG') else '.jpg'
    asset=path.parent/('image-'+sha[:16]+suffix)
    with state.locked(root):
        if state.file_hash(path)!=before:raise state.StateConflict('draft changed during image generation')
        state.audited_write(asset,data,state.file_hash(asset),root=root,operation='approved_image_generated',body_sha=sha)
        doc.update(image_path=str(asset),image_body_sha256=sha)
        state.audited_json(path,doc,before,root=root,operation='image_bound_to_approved_body',body_sha=sha)
    return {'ok':True,'phase':'IMAGE_READY','image':str(asset),'publish_performed':False}


def image_fallback(path,sha,exc,*,root=state.ROOT,db_path=None,jobs_path=state.JOBS):
    """Owner preference: continue text-only when image generation fails."""
    if isinstance(exc,state.StateConflict):raise exc
    from workflow_routing import failure_code
    code=failure_code(exc)
    with state.locked(root):
        status=state.inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
        if status['body_sha256']!=sha or not status['owner_approved'] or not status['reviews_ready'] or status['published']:
            raise state.StateConflict('post changed or is not eligible for image fallback')
        before=state.file_hash(path);doc=state.read(path)
        doc.update(image_required=False,image_path=None,image_sha256=None,image_body_sha256=None,
                   image_fallback_reason=code)
        state.audited_json(path,doc,before,root=root,operation='owner_preference_text_only_on_image_failure',body_sha=sha)
    return {'ok':True,'phase':'IMAGE_UNAVAILABLE_TEXT_ONLY','reason':code,
            'message':'Image generation was unavailable ('+code+'); continuing with text only.'}


def current_approval_message(*,db_path=None):
    from hermes_diagnostics import current_contract
    from hermes_owner_context import human_text
    contract=current_contract();key=contract.get('session_key');message=human_text(contract.get('latest_human_message',''))
    if not key or not message or contract.get('turn_origin')=='synthetic_event':raise ValueError('current authenticated owner approval message required')
    path=Path(db_path or state.HOME/'state.db')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
        rows=con.execute("SELECT m.id,m.session_id,m.content FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.role='user' AND m.platform_message_id IS NOT NULL AND s.source='discord' AND s.user_id=? ORDER BY m.id DESC LIMIT 200",(state.consent.OWNER_DISCORD_ID,)).fetchall()
    for mid,sid,content in rows:
        if hashlib.sha256(sid.encode()).hexdigest()==key and human_text(content)==message:return mid
    raise ValueError('current owner message could not be matched to authenticated Discord history')


def retry_chat_approval(body,*,db_path=None):
    """Resolve a retry to the immediately preceding owner instruction in this session."""
    from hermes_diagnostics import current_contract
    from hermes_owner_context import human_text
    from linkedin_conversation import has_draft_body
    contract=current_contract();message=human_text(contract.get('latest_human_message',''))
    if not re.match(r'(?i)^try again(?:[.! ]*(?:\n|$))',message):
        raise ValueError('An authenticated instruction to publish now or at a specific time is required')
    current=current_approval_message(db_path=db_path)
    path=Path(db_path or state.HOME/'state.db')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
        row=con.execute("SELECT session_id FROM messages WHERE id=? AND role='user'",(current,)).fetchone()
        if not row:raise ValueError('Retry message unavailable')
        previous=con.execute("SELECT id FROM messages WHERE session_id=? AND role='user' AND id<? ORDER BY id DESC LIMIT 1",(row[0],current)).fetchone()
        if not previous:raise ValueError('No previous owner instruction to retry')
        approval=state.consent.verify_message(previous[0],body,db_path=db_path)
        if not approval['ok']:raise ValueError(approval['reason'])
        # A clearly presented new version after approval invalidates a retry of the old version.
        for (content,) in con.execute("SELECT content FROM messages WHERE session_id=? AND role='assistant' AND id>? AND id<? ORDER BY id",(row[0],previous[0],current)):
            text=content or ''
            if ('```' in text or re.search(r'(?i)\b(?:revised post|updated post|final text)\s*:',text)) and has_draft_body(text) and not state.consent._presented(text,body):
                raise ValueError('A newer draft was presented after approval; please review it')
    spoken=approval['receipt']['preferences']
    if not (spoken.get('publish_now') or spoken.get('publish_at')):raise ValueError('Previous approval has no publication time')
    return previous[0],approval


def publish_now(row,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,runner=None,verified_instruction=None):
    from hermes_diagnostics import current_contract
    from hermes_owner_context import human_text
    message=human_text(current_contract().get('latest_human_message',''))
    from linkedin_conversation import interpret
    spoken=interpret(message)
    if verified_instruction is not None:
        message_id,approved=verified_instruction
        proof=state.consent.verify_message(message_id,state.body_of(state.read(Path(row['captured_artifact']))),db_path=db_path)
        if not proof['ok']:raise ValueError(proof['reason'])
        spoken=proof['receipt']['preferences']
    else:message_id=current_approval_message(db_path=db_path)
    if not spoken['approved'] or not spoken['publish_now']:raise ValueError('Tell me explicitly if you want this post published now.')
    path=Path(row.get('captured_artifact') or (row.get('artifact') if row.get('source_kind')=='DATED_ARTIFACT' else None) or (Path(root)/'drafts'/f"approved_{date.fromisoformat(row['date']):%Y%m%d}_{row['day']}"/'linkedin_drafts.json'))
    status=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
    if status['published']:return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False,'network_calls':0}
    if spoken.get('skip_image') and status['owner_approved'] and status['body_sha256']==row['body_sha256']:
        with state.locked(root):
            before=state.file_hash(path);doc=state.read(path)
            doc.update(image_required=False,image_path=None,image_sha256=None,image_body_sha256=None,
                       preference_message_id=message_id)
            state.audited_json(path,doc,before,root=root,operation='owner_requested_text_only_publication',body_sha=row['body_sha256'])
        status=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
    if not state.publishing_enabled(root) or not status['content_ready'] or status['body_sha256']!=row['body_sha256']:raise ValueError('Cannot publish: '+', '.join(status['content_blockers'] or ['publishing_policy_or_version']))
    if row['date']!=datetime.now(state.LONDON).date().isoformat():raise ValueError('publish-now cannot move a dated post to another day')
    import subprocess,sys
    doc=state.read(path);command=[sys.executable,str(state.REPO/'career-ops/linkedin_publish.py'),'publish','--drafts',str(path),'--approve-publish','--confirm-token',row['body_sha256'],'--max-retries','0']
    if doc.get('image_path'):command+=['--image',doc['image_path']]
    if runner is None and Path(root).resolve()!=state.ROOT.resolve():raise ValueError('private fixture requires an injected publisher')
    result=(runner or subprocess.run)(command,cwd=str(state.REPO),capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:payload=json.loads(result.stdout)
    except ValueError:payload={}
    verified=bool(result.returncode==0 and payload.get('performed') and payload.get('post_urn') and state.published(row['body_sha256'],root))
    return {'ok':verified,'phase':'PUBLISHED' if verified else 'PUBLISH_FAILED','publish_performed':verified,
        'post_urn':payload.get('post_urn') if verified else None,'child_exit_code':result.returncode,
        'blocker_category':payload.get('blocker_category'),'network_calls':payload.get('network_calls_spent')}


def linkedin(args,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,generator=None,now=None,runner=None,personal_runner=None,news_runner=None):
    now=now or datetime.now(state.LONDON)
    mode=args.get('action','show')
    if mode not in ('show','build','prepare','approve','image','plan','publish','publish_chat','draft_chat','review'):raise ValueError('unsupported LinkedIn action')
    opts={'root':root,'jobs_path':jobs_path,'db_path':db_path,'week_of':args.get('week_of')}
    if mode in ('show','build'):
        result=show(**opts)  # Both actions are read-only; neither imports a chat draft.
        if mode=='build' and (args.get('body_sha256') or args.get('post_id')):
            candidates=[]
            for row in result['days']:
                if args.get('day') and row.get('day')!=args['day']:continue
                candidates.extend([row,*row.get('alternatives',[])])
            if not any((not args.get('body_sha256') or x.get('body_sha256')==args['body_sha256']) and (not args.get('post_id') or x.get('post_id')==args['post_id']) for x in candidates):
                return {'ok':False,'phase':'DRAFT_NOT_FOUND','reason':'build is read-only; use draft_chat for new or revised text','publish_performed':False,'network_calls':0,'writes':0}
        return result
    if mode=='prepare':
        import linkedin_weekly
        monday=args.get('week_of') or show(**opts)['week_of']
        doc=linkedin_weekly.prepare(monday,root=root)
        return {'ok':bool(doc['ok']),'preparation':show(**opts),'publish_performed':False}
    if mode=='draft_chat':
        body=args.get('post_text');sources=args.get('sources') or []
        if not isinstance(body,str) or not body.strip() or len(body.strip())>=1000:raise ValueError('A post under 1000 characters is required')
        if not isinstance(sources,list) or any(not isinstance(u,str) or not u.startswith('https://') for u in sources):raise ValueError('sources must be HTTPS URLs')
        from hermes_diagnostics import current_contract
        contract=current_contract()
        if contract.get('workflow')!='linkedin' or contract.get('turn_origin')!='human_text':raise ValueError('An authenticated owner draft request is required')
        if Path(root).resolve()==state.ROOT.resolve():current_approval_message(db_path=db_path)
        body=body.strip();sha=state.consent.digest(body)
        requested_id=args.get('post_id')
        if requested_id:
            existing=_selected(None,None,post_id=requested_id,root=root,jobs_path=jobs_path,db_path=db_path)
            if existing.get('source_kind')!='DATED_ARTIFACT' or existing.get('owner_approved') or existing.get('published') or existing.get('slot_matches'):
                raise ValueError('Only an unapproved, unscheduled chat draft can be edited in place')
            target=date.fromisoformat(existing['date']);day=existing['day'];path=Path(existing['artifact'])
            if args.get('target_date') and args['target_date']!=target.isoformat():raise ValueError('Changing a post date requires a separate scheduling action')
            with state.locked(root):
                before=state.file_hash(path);doc=state.read(path)
                if doc.get('post_id')!=requested_id or doc.get('owner_approval'):raise state.StateConflict('draft changed while editing')
                doc.update(post_text=body,approved=False,news_fact_gate={'sources':sources},personal_fact_gate={})
                state.audited_json(path,doc,before,root=root,operation='chat_draft_revised',body_sha=sha)
            return {'ok':True,'phase':'AWAITING_OWNER_APPROVAL','post_id':requested_id,'body_sha256':sha,
                    'artifact':str(path),'owner_approved':False,'publish_performed':False}
        target=date.fromisoformat(args.get('target_date') or now.date().isoformat());day=target.strftime('%A').lower()
        path=Path(root)/'drafts'/f'approved_{target:%Y%m%d}_{day}_{sha}'/'linkedin_drafts.json'
        with state.locked(root):
            before=state.file_hash(path)
            if before:
                doc=state.read(path)
                if state.body_of(doc)!=body or not doc.get('post_id'):raise state.StateConflict('existing artifact cannot be reused as a new post')
            else:
                import uuid
                doc={'schema_version':2,'post_id':uuid.uuid4().hex,'post_text':body,'day':day,
                     'approved':False,'news_fact_gate':{'sources':sources},'personal_fact_gate':{}}
                state.audited_json(path,doc,None,root=root,operation='chat_draft_registered',body_sha=sha)
        return {'ok':True,'phase':'AWAITING_OWNER_APPROVAL','post_id':doc['post_id'],'body_sha256':sha,
                'artifact':str(path),'owner_approved':False,'publish_performed':False}
    if mode=='publish_chat':
        body=args.get('post_text');sources=args.get('sources') or []
        if not isinstance(body,str) or not body.strip() or len(body.strip())>=1000:raise ValueError('A displayed post under 1000 characters is required')
        if not isinstance(sources,list) or any(not isinstance(u,str) or not u.startswith('https://') for u in sources):raise ValueError('sources must be HTTPS URLs')
        from hermes_diagnostics import current_contract
        from linkedin_conversation import interpret
        spoken=interpret(current_contract().get('latest_human_message',''))
        retry=False
        if not spoken['approved'] or not (spoken['publish_now'] or spoken['publish_at']):
            message_id,approval=retry_chat_approval(body,db_path=db_path);retry=True
        else:
            message_id=args.get('approval_message_id')
            if isinstance(message_id,str) and message_id.isdigit():message_id=int(message_id)
            if not message_id or message_id > 9007199254740991:message_id=current_approval_message(db_path=db_path)
            approval=state.consent.verify_message(message_id,body,db_path=db_path)
            if not approval['ok']:raise ValueError(approval['reason'])
        spoken=approval['receipt']['preferences']
        if state.published(state.consent.digest(body),root):return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False}
        import linkedin_weekly  # installs the existing scripts and content-generator paths
        from topic_reuse_check import check_text
        if check_text(body,registry_path=Path(root)/'topic_registry.json')['blocked']:raise ValueError('topic already used or excluded')
        due=datetime.fromisoformat(spoken['publish_at']) if spoken['publish_at'] else None
        target=(due.date() if due else now.date()).isoformat()
        registered=None
        if args.get('post_id'):
            registered=_selected(None,state.consent.digest(body),post_id=args['post_id'],root=root,jobs_path=jobs_path,db_path=db_path)
            if registered['date']!=target:raise ValueError('post ID date does not match the requested publication date')
        result=state.capture(body,target,message_id,sources=sources,distinct=True,post_id=args.get('post_id'),artifact_path=registered['artifact'] if registered else None,root=root,db_path=db_path)
        path=Path(result['artifact'])
        with state.locked(root):
            before=state.file_hash(path);doc=state.read(path)
            doc['image_required']=not spoken.get('skip_image',False)
            if due:doc['requested_publish_at']=due.isoformat()
            state.audited_json(path,doc,before,root=root,operation='chat_publication_preferences',body_sha=result['body_sha256'])
        import linkedin_content_gen as gen
        status=state.reconcile(path,root=root,db_path=db_path,jobs_path=jobs_path,
            personal_runner=state._personal_runner,news_runner=gen.factcheck_post)
        if not status['reviews_ready']:
            return {'ok':True,'phase':'APPROVED_BUT_BLOCKED','approval':result,'content_blockers':status['content_blockers'],
                    'review_errors':status.get('review_errors',[]),'publish_performed':False}
        row={'date':target,'day':date.fromisoformat(target).strftime('%A').lower(),'body_sha256':result['body_sha256'],'captured_artifact':str(path)}
        image_result={'ok':True,'phase':'IMAGE_SKIPPED'}
        if not spoken.get('skip_image',False):
            try:image_result=image(row,root=root,jobs_path=jobs_path,db_path=db_path,generator=generator)
            except Exception as exc:image_result=image_fallback(path,row['body_sha256'],exc,root=root,db_path=db_path,jobs_path=jobs_path)
        if due:
            if due<=now:return {'ok':True,'phase':'APPROVED_READY_NEEDS_PUBLISH_INSTRUCTION','approval':result,'message':'Approval is saved, but the requested time has passed.','publish_performed':False}
            plan=state.plan_slot(path,target,root=root,db_path=db_path,jobs_path=jobs_path,now=now)
            armed=any(item.get('day')==row['day'] and item.get('next_run_at')==due.isoformat() for item in (plan.get('publishing') or {}).get('armed',[]))
            return {'ok':True,'phase':'SCHEDULED' if armed else 'APPROVED_READY_PAUSED','approval':result,'plan':plan,'image':image_result,'publish_performed':False}
        return {**publish_now(row,root=root,jobs_path=jobs_path,db_path=db_path,runner=runner,verified_instruction=(message_id,approval) if retry else None),'image':image_result}
    row=_selected(args.get('day'),args.get('body_sha256'),post_id=args.get('post_id'),**opts)
    if row.get('published'):return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False,'network_calls':0}
    if mode=='review':
        if row.get('source_kind')!='DATED_ARTIFACT' or not row.get('owner_approved'):raise ValueError('review requires an approved dated artifact')
        path=Path(row['artifact']);new_sources=args.get('sources')
        if new_sources is not None:
            if not isinstance(new_sources,list) or any(not isinstance(u,str) or not u.startswith('https://') for u in new_sources):raise ValueError('sources must be HTTPS URLs')
            with state.locked(root):
                before=state.file_hash(path);doc=state.read(path)
                body=state.body_of(doc)
                if state.consent.digest(body)!=row['body_sha256'] or doc.get('cancelled') or not state.consent.verify_receipt(doc.get('owner_approval'),body,db_path=db_path)['ok']:
                    raise state.StateConflict('draft or approval changed before review')
                prior=doc.get('news_fact_gate') or {}
                if set(prior.get('sources') or [])!=set(new_sources):doc['news_fact_gate']={'sources':new_sources}
                state.audited_json(path,doc,before,root=root,operation='review_sources_recorded',body_sha=row['body_sha256'])
        if Path(root).resolve()==state.ROOT.resolve():
            import linkedin_content_gen as gen
            personal_runner=personal_runner or state._personal_runner;news_runner=news_runner or gen.factcheck_post
        status=state.reconcile(path,root=root,db_path=db_path,jobs_path=jobs_path,personal_runner=personal_runner,news_runner=news_runner)
        return {'ok':True,'phase':status['phase'],'post_id':row.get('post_id'),'review':status,'publish_performed':False}
    requested_publish=(mode=='publish')
    if mode in ('approve','publish'):
        if row['source_kind'] in ('REVIEWED_PREPARED','PREPARED'):
            source=state.read(row['artifact'])['posts'][row['day']]
        else:source=state.read(row['artifact'])
        message_id=args.get('approval_message_id')
        if isinstance(message_id,str) and message_id.isdigit():message_id=int(message_id)
        if not message_id or message_id > 9007199254740991:message_id=current_approval_message(db_path=db_path)
        approval=state.consent.verify_message(message_id,row['post_text'],db_path=db_path)
        preferences=(approval.get('receipt') or {}).get('preferences') or approval.get('preferences') or {}
        requested_publish=requested_publish or preferences.get('publish_now',False)
        skip_image=preferences.get('skip_image',False) or source.get('image_required') is False
        capture_id=message_id
        if not approval['ok']:
            existing=state.consent.verify_receipt(source.get('owner_approval'),row['post_text'],db_path=db_path)
            if not (approval.get('authenticated_owner') and existing['ok'] and
                    (preferences.get('skip_image') or preferences.get('publish_at'))):
                raise ValueError(approval['reason'])
            capture_id=existing['receipt']['hermes_message_id']
        due=datetime.fromisoformat(preferences.get('publish_at') or source['requested_publish_at']) if (preferences.get('publish_at') or source.get('requested_publish_at')) else datetime.combine(date.fromisoformat(row['date']),state.time(8),state.LONDON)
        target=due.date().isoformat()
        target_path=Path(root)/'drafts'/f"approved_{due:%Y%m%d}_{due.strftime('%A').lower()}"/'linkedin_drafts.json'
        conflict=target!=row['date'] and target_path.exists() and state.body_of(state.read(target_path))!=row['post_text']
        capture_target=row['date'] if conflict else target
        selected_path=row.get('artifact') if row.get('source_kind')=='DATED_ARTIFACT' and capture_target==row['date'] else None
        result=state.capture(row['post_text'],capture_target,capture_id,replace=(capture_target==row['date']),distinct=bool(row.get('post_id') and row.get('source_kind') in ('PREPARED','REVIEWED_PREPARED')),post_id=row.get('post_id'),artifact_path=selected_path,root=root,db_path=db_path)
        path=Path(result['artifact'])
        with state.locked(root):
            before=state.file_hash(path);doc=state.read(path)
            if state.consent.digest(state.body_of(doc))!=row['body_sha256']:raise state.StateConflict('captured version changed')
            existing_news=source.get('news_fact_gate') or {}
            supplied_sources=args.get('sources')
            if supplied_sources is not None:
                if not isinstance(supplied_sources,list) or any(not isinstance(u,str) or not u.startswith('https://') for u in supplied_sources):raise ValueError('sources must be HTTPS URLs')
                if set(existing_news.get('sources') or [])!=set(supplied_sources):existing_news={'sources':supplied_sources}
            doc.update(news_fact_gate=existing_news,personal_fact_gate=source.get('personal_fact_gate'),
                       image_required=not skip_image,requested_publish_at=due.isoformat(),
                       preference_message_id=message_id)
            # Preserve independently authenticated override consent across date/image changes.
            old_override=source.get('owner_override')
            if isinstance(old_override,dict) and old_override.get('body_sha256')==row['body_sha256']:
                old_receipt=old_override.get('receipt') or source.get('owner_approval')
                if state.consent.verify_receipt(old_receipt,row['post_text'],db_path=db_path,require_override=True)['ok']:
                    doc['owner_override']={**old_override,'receipt':old_receipt}
            if skip_image:doc.update(image_path=None,image_sha256=None,image_body_sha256=None)
            if preferences.get('override'):
                override=state.consent.verify_message(message_id,row['post_text'],db_path=db_path,require_override=True)
                if override['ok']:
                    doc['owner_override']={'approved_by':'Mukund','body_sha256':row['body_sha256'],
                        'reason':'Owner explicitly acknowledged the fact-check warning and approved this exact version despite it.',
                        'receipt':override['receipt']}
            state.audited_json(path,doc,before,root=root,operation='natural_owner_approval_and_preferences',body_sha=row['body_sha256'])
        status=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
        if not status['reviews_ready']:
            if Path(root).resolve()==state.ROOT.resolve():
                import linkedin_content_gen as gen
                personal_runner=personal_runner or state._personal_runner;news_runner=news_runner or gen.factcheck_post
            if personal_runner or news_runner:
                status=state.reconcile(path,root=root,db_path=db_path,jobs_path=jobs_path,personal_runner=personal_runner,news_runner=news_runner)
        if not status['reviews_ready']:
            return {'ok':True,'phase':'APPROVED_BUT_BLOCKED','message':'Your approval is saved. Review remains incomplete or blocked; do not approve the unchanged text again.',
                    'approval':result,'content_blockers':status['content_blockers'],'review_errors':status.get('review_errors',[]),'news_review_detail':status.get('news_review_detail'),'publish_performed':False}
        if conflict:
            return {'ok':True,'phase':'SCHEDULE_CONFLICT','message':'Your approval is saved. Another post already has that date. Which post should use that slot?',
                    'approval':result,'publish_performed':False}
        selected={**row,'date':capture_target,'day':due.strftime('%A').lower(),'captured_artifact':str(path)}
        image_result={'ok':True,'phase':'IMAGE_SKIPPED'}
        if not skip_image:
            try:image_result=image(selected,root=root,jobs_path=jobs_path,db_path=db_path,generator=generator)
            except Exception as exc:image_result=image_fallback(path,row['body_sha256'],exc,root=root,db_path=db_path,jobs_path=jobs_path)
        if requested_publish:
            return {**publish_now(selected,root=root,jobs_path=jobs_path,db_path=db_path,runner=runner),'image':image_result}
        if due<=now:
            return {'ok':True,'phase':'APPROVED_READY_NEEDS_PUBLISH_INSTRUCTION','approval':result,'image':image_result,
                    'message':'Your approval is saved. That time has passed; tell me when you want it posted.','publish_performed':False}
        return {'ok':True,'approval':result,'image':image_result,
                'plan':state.plan_slot(path,capture_target,root=root,db_path=db_path,jobs_path=jobs_path),'publish_performed':False}
    if mode=='publish':return publish_now(row,root=root,jobs_path=jobs_path,db_path=db_path)
    if mode=='image':return image(row,root=root,jobs_path=jobs_path,db_path=db_path,generator=generator)
    if mode=='plan':
        path=Path(row['artifact']) if row.get('source_kind')=='DATED_ARTIFACT' else Path(root)/'drafts'/f"approved_{date.fromisoformat(row['date']):%Y%m%d}_{row['day']}"/'linkedin_drafts.json'
        return {'ok':True,'plan':state.plan_slot(path,row['date'],root=root,db_path=db_path,jobs_path=jobs_path),'publish_performed':False}
    raise ValueError('unsupported LinkedIn action')


def search_report(*,home=state.HOME,repo=state.REPO):
    from hermes_diagnostics import latest_run
    home=Path(home);job=latest_run('5a66e1129e58',home=home);execution=job.get('execution') or {}
    phase='PAUSED' if job.get('job_enabled') is False else 'RUNNING' if execution.get('status') in ('running','claimed') else str(execution.get('status') or 'UNKNOWN').upper()
    complete=None;db=home/'cron/executions.db'
    if db.exists():
        with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as con:
            con.row_factory=sqlite3.Row
            r=con.execute("SELECT id,status,finished_at FROM executions WHERE job_id=? AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1",('5a66e1129e58',)).fetchone()
            complete=dict(r) if r else None
    prior=None
    if complete:
        finished=datetime.fromisoformat(complete['finished_at'].replace('Z','+00:00'));candidates=[]
        for p in (Path(repo)/'runtime/career-ops/job-scan-runs').glob('*.json'):
            try:stamp=datetime.strptime(p.name[:16],'%Y%m%dT%H%M%SZ').replace(tzinfo=finished.tzinfo)
            except ValueError:continue
            if abs((stamp-finished).total_seconds())<=120:candidates.append((abs((stamp-finished).total_seconds()),p))
        if candidates:
            p=min(candidates,key=lambda r:r[0])[1];d=state.read(p);coverage=d.get('coverage') or {}
            writes=[]
            for line in str(d.get('stdout') or '').splitlines():
                if line.startswith('TRACKER_WRITE_RESULT '):
                    try:v=json.loads(line.split(' ',1)[1]);writes.append({k:v.get(k) for k in ('applied','counts','verification_ok')})
                    except ValueError:pass
            prior={'execution':complete,'path':str(p),'exit_code':d.get('exit_code'),'coverage_complete':coverage.get('coverage_complete'),
                'completed_batches':coverage.get('completed_batches'),'batches_attempted':coverage.get('batches_attempted'),'verified_writer_results':writes,
                'silent_delivery':job.get('available') and not bool(job.get('structured_result'))}
    result={'schema_version':1,'workflow':'career_search','checked_at':datetime.now(state.LONDON).isoformat(),'phase':phase,'latest_execution':job,
        'last_completed_scan':prior,'network_calls':0,'writes':0,'authority':'exact scheduler execution and matching delta-run schema; missing evidence is UNKNOWN'}
    result['evidence_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest();return result


def render_search(doc):
    lines=['UK job search: '+doc['phase']+'. Checked '+doc['checked_at']+'.']
    prior=doc.get('last_completed_scan')
    if prior:lines+=['Last completed scan: '+str(prior['execution']['finished_at'])+'; exit '+str(prior['exit_code'])+'; completed batches '+str(prior['completed_batches'])+'; complete coverage '+str(prior['coverage_complete'])+'.','Verified tracker write results: '+json.dumps(prior['verified_writer_results'])+'. No new-job total is inferred from missing report fields.']
    else:lines+=['No matching completed scan artifact is available; older failures are not substituted.']
    lines+=['Evidence: '+doc['evidence_sha256'][:16]+'. This report did not start or stop a scan.']
    return '\n\n'.join(lines)


def guard(tool_name,args=None,**kwargs):
    from hermes_diagnostics import current_contract
    c=current_contract();args=args or {}
    if c.get('workflow')!='linkedin':return None
    if tool_name not in ('terminal','write_file','execute_code','python','patch'):return None
    payload=json.dumps(args).lower()
    if tool_name!='terminal' or re.search(r'python|pythob|gen_images|execute_code|<<|powershell.*-c|pwsh.*-c|set-content|writealltext|out-file|>\s*[^&]',payload):
        return {'action':'block','message':'Use career_linkedin_workflow for this LinkedIn stage (show/build/prepare/image/approve/plan). It preserves exact versions, review provenance and the supported Hermes image router. Do not create scratch compilers or use the retired desktop bot. Read-only shell inspection remains available outside the bounded stage.'}
    return None
