"""Resumable weekly LinkedIn preparation. Never approves, images, arms or publishes."""
from __future__ import annotations
import argparse,json,sys
from datetime import date,datetime,timedelta
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'exec-brain'))
sys.path.insert(0,str(REPO/'scripts'))
import linkedin_content_gen as gen
import linkedin_state as state
import linkedin_factcheck as fc
from topic_reuse_check import check_text,load_registry
from router_brain import RouterDecisionError
from workflow_control import run_stage
from hermes_owner_context import retrieve


def accepted(post):
    body=post.get('post_text') or ''
    return (bool(body.strip()) and len(body)<1000 and not post.get('blocked')
        and post.get('phase') not in ('BLOCKED','REVIEWING') and not post.get('error')
        and fc.provenance_ok(post.get('news_fact_gate'),body)[0]
        and state.personal_ok(post.get('personal_fact_gate'),body))


def complete_reviews(post,*,label,context_hash):
    """One bounded wording correction, with both gates rerun on changed text.

    The existing personal verifier stays intact; no rejected claim is waived.
    Repaired text remains unapproved and has its own exact-body hashes.
    """
    post=dict(post);attempts=[]
    for attempt in range(2):
        body=post.get('post_text') or '';reviewed=[]
        def check():
            gate=state._personal_runner(body,label)
            reviewed.append(gate);return gate
        try:
            pg,_=run_stage('career.linkedin','personal-review',{'post':body,'profile_sha256':context_hash},
                check,lambda g:state.personal_ok(g,body))
        except RouterDecisionError as exc:
            if str(exc)!='stage_validation_failed' or not reviewed:raise
            pg=reviewed[0]
        attempts.append({'body_sha256':state.consent.digest(body),'verdict':pg.get('verdict'),'post_text':body,'personal_fact_gate':pg})
        post['personal_fact_gate']=pg
        if state.personal_ok(pg,body):
            post['personal_review_attempts']=attempts;return post
        if attempt or pg.get('available') is False or not (pg.get('unsupportedFacts') or pg.get('invented') or pg.get('forbidden')):
            raise RouterDecisionError('linkedin_personal_review_blocked')
        topic=post.get('topic') or {};sources=topic.get('sources') or []
        actual=fc.combine_sources({u:fc.cached_source_text(u) for u in sources if fc.cached_source_text(u)})
        instruction=('Correct the previous unapproved LinkedIn draft. Preserve only supported facts. '
            'The personal verifier rejected the wording below. Remove unsupported candidate claims. '
            'If a third-party description resembles a candidate tool claim, rephrase it clearly as third-party reporting. '
            'Do not invent a replacement skill, achievement, experience or tool. Keep under 1000 characters. '
            'Return the complete corrected post, without comments.\n'
            +json.dumps({'previous_draft':body,'personal_review':pg,'actual_news_sources':actual},ensure_ascii=False))
        evidence=({k:v for k,v in topic.items() if k!='research_receipt'},topic['research_receipt']) if topic.get('research_receipt') else None
        changed=gen.generate_linkedin_content(instruction,source_type='verified draft correction',source_evidence=evidence)
        if not changed.strip() or len(changed)>=1000:raise RouterDecisionError('linkedin_post_length_exceeded')
        ng,_=run_stage('career.linkedin','factual-review',{'post':changed,'sources':sources},
            lambda:gen.factcheck_post(changed,sources),lambda g:isinstance(g,dict) and g.get('verdict')=='pass')
        post.update(post_text=changed,news_fact_gate=ng,blocked=False)
    raise RouterDecisionError('linkedin_personal_review_blocked')


def personal_reflection(exclusions,*,record=lambda value:None):
    instruction=('Write a fresh personal professional reflection using only the supplied authoritative profile. '
        'Do not invent an incident, conversation, date, workplace achievement or recent action. '
        'Use a real owner preference or ambition and clearly personal judgement. Do not assert external world facts. '
        'Avoid these exhausted topics and angles: '+exclusions)
    attempts=[]
    for attempt in range(2):
        body=gen.generate_linkedin_content(instruction,source_type='verified professional profile')
        post={'post_text':body,'blocked':True};reviewed=[]
        # Preserve the exact draft and actual verdict even when stage validation
        # rejects it. Failure evidence must not disappear behind a generic error.
        record({**post,'phase':'REVIEWING','reflection_attempts':list(attempts)})
        def check():
            gate=gen.factcheck_post(body,[]);reviewed.append(gate)
            record({**post,'phase':'REVIEWING','news_fact_gate':gate,'reflection_attempts':list(attempts)})
            return gate
        try:
            gate,_=run_stage('career.linkedin','factual-review',{'post':body,'sources':[]},check,
                lambda g:isinstance(g,dict) and g.get('verdict')=='pass')
        except RouterDecisionError as exc:
            if str(exc)!='stage_validation_failed' or not reviewed:raise
            gate=reviewed[0]
        attempts.append({'body_sha256':state.consent.digest(body),'verdict':gate.get('verdict'),'post_text':body,'news_fact_gate':gate})
        if gate.get('verdict')=='pass':
            return {**post,'news_fact_gate':gate,'blocked':False,'reflection_attempts':attempts}
        # A real source-less review found checkable external assertions. Give
        # those precise findings to the writer once; do not waive them or retry
        # unavailable judges, exhausted providers or failed source reads.
        if attempt or not gate.get('llm_used') or not gate.get('world_claims'):raise RouterDecisionError('linkedin_reflection_review_blocked')
        instruction=('Revise this personal reflection to remove the specific unsupported external-world assertions. '
            'Keep only verified personal facts and clearly first-person opinions or aspirations. '
            'Do not replace a removed claim with a new claim or revisit these exhausted topics: '+exclusions+'\n'
            +json.dumps({'previous_draft':body,'world_claims':gate['world_claims']},ensure_ascii=False))
    raise RouterDecisionError('linkedin_reflection_review_blocked')


def prepare(week_of=None,*,root=state.ROOT):
    root=Path(root);today=datetime.now(state.LONDON).date()
    monday=date.fromisoformat(week_of) if week_of else today+timedelta(days=(7-today.weekday())%7)
    if monday.weekday()!=0:raise ValueError('week-of must be Monday')
    folder=root/'review'/monday.isoformat();folder.mkdir(parents=True,exist_ok=True)
    output=folder/'weekly.json'
    context,evidence=retrieve('Write my LinkedIn post')
    if not context or not evidence or not all(e.get('complete') for e in evidence):raise RouterDecisionError('linkedin_profile_incomplete')
    context_hash=fc.sha256_text(context)
    registry_path=root/'topic_registry.json';registry=load_registry(registry_path)
    with state.locked(folder):
        doc=state.read(output) if output.exists() else {'schema_version':1,'week_of':monday.isoformat(),'posts':{},'research':{}}
        doc.update(profile_context_sha256=context_hash,profile_evidence=evidence,
            profile_source='authoritative_local_professional_references',
            live_linkedin_profile_read=False,live_profile_limitation='No approved full-profile read API; using complete local verified professional references',
            publishing_enabled=state.publishing_enabled(root),publish_performed=False,images_generated=0)
        def checkpoint():
            state.audited_json(output,doc,state.file_hash(output),root=folder,operation='weekly_preparation',body_sha=None)
        checkpoint()
        for offset,day,category in [(1,'tuesday','ai_cyber'),(2,'wednesday','ai_noncyber'),(3,'thursday','personal')]:
            target=monday+timedelta(days=offset)
            canonical=root/'drafts'/f'approved_{target:%Y%m%d}_{day}'/'linkedin_drafts.json'
            if canonical.exists():
                existing=state.inspect_artifact(canonical,root=root)
                if existing['owner_approved']:
                    doc['posts'][day]={'phase':existing['phase'],'category':category,'post_text':state.body_of(state.read(canonical)),
                        'body_sha256':existing['body_sha256'],'canonical_artifact':str(canonical),'owner_approved':True,'content_ready':existing['content_ready']}
                    checkpoint();continue
            old=doc['posts'].get(day) or {}
            if old.get('profile_context_sha256')==context_hash and accepted(old) and not check_text(old['post_text'],registry_path=registry_path)['blocked']:
                continue
            try:
                if category!='personal':
                    topics=doc['research'].get(category)
                    if not topics:
                        topics=gen.research_trending_topics(2,category=category)
                        doc['research'][category]=topics;checkpoint()
                    candidates=[]
                    for topic in topics:
                        if check_text(topic['title']+' '+topic['summary'],registry_path=registry_path)['blocked']:continue
                        if gen.cache_topic_sources(topic).get('cached'):candidates.append(topic)
                    if not candidates:raise RouterDecisionError('linkedin_sources_unreadable')
                    post=gen.generate_post_from_topic(candidates[0],generate_image=False)
                else:
                    exclusions=json.dumps([e.get('topic') for e in registry.get('topics',[]) if e.get('status') in ('used','retired')],ensure_ascii=False)
                    def record_attempt(value):
                        doc['posts'][day]={**value,'category':category,'owner_approved':False}
                        checkpoint()
                    post=personal_reflection(exclusions,record=record_attempt)
                post.pop('image_bytes',None);body=post.get('post_text') or ''
                if check_text(body,registry_path=registry_path)['blocked']:raise RouterDecisionError('linkedin_topic_reused')
                if len(body)>=1000:raise RouterDecisionError('linkedin_post_length_exceeded')
                if post.get('blocked'):raise RouterDecisionError('linkedin_news_review_blocked')
                post=complete_reviews(post,label='linkedin-weekly-'+day,context_hash=context_hash)
                body=post['post_text']
                if check_text(body,registry_path=registry_path)['blocked']:raise RouterDecisionError('linkedin_topic_reused')
                post.update(body_sha256=state.consent.digest(body),category=category,
                    profile_context_sha256=context_hash,target_date=target.isoformat(),phase='AWAITING_OWNER_APPROVAL',owner_approved=False)
                if not accepted(post):raise RouterDecisionError('linkedin_review_incomplete')
                doc['posts'][day]=post
            except Exception as exc:
                from workflow_routing import failure_code
                doc['posts'][day]={**(doc['posts'].get(day) or {}),'phase':'BLOCKED','category':category,'error':failure_code(exc),'owner_approved':False}
                checkpoint()
                # Keep completed slots, but never spend quota on later slots after
                # a quota/auth/provider failure. A content issue can be reviewed.
                if any(w in failure_code(exc) for w in ('usage_limit','quota','auth','billing','unavailable','timeout')):break
            checkpoint()
        doc['ready_count']=sum(bool(p.get('owner_approved') and p.get('content_ready')) or accepted(p) for p in doc['posts'].values())
        doc['ok']=doc['ready_count']==3
        checkpoint();return doc


def render(doc):
    lines=['LinkedIn weekly drafts — '+doc['week_of'],
        'Profile: complete local verified professional references; live profile unavailable.',
        'Publishing enabled: '+str(doc.get('publishing_enabled'))+'. New text still requires exact owner approval.']
    for day in ('tuesday','wednesday','thursday'):
        post=doc['posts'].get(day) or {'phase':'NOT_COMPLETED'}
        lines+=['',day.title()+': '+post['phase']]
        if post.get('post_text') and (post.get('owner_approved') or post.get('phase')=='AWAITING_OWNER_APPROVAL'):
            lines += ['',post['post_text']]
            if not post.get('owner_approved'):lines += ['','Tell me naturally if you approve this post and when you want it published.']
            else:lines += ['','Existing exact owner approval preserved.']
        elif post.get('error'):lines += ['Reason: '+post['error']]
    return '\n'.join(lines)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--week-of');p.add_argument('--json',action='store_true');a=p.parse_args(argv)
    try:
        doc=prepare(a.week_of);print(json.dumps(doc,indent=2,ensure_ascii=False) if a.json else render(doc))
        return 0 if doc['ok'] else 1
    except (OSError,ValueError,RouterDecisionError) as exc:
        from workflow_routing import failure_code
        print(json.dumps({'ok':False,'error':failure_code(exc),'publish_performed':False}));return 1


if __name__=='__main__':raise SystemExit(main())
