"""Bounded research-stage adapters for the existing LinkedIn workflow.

Hermes keeps planning/review authority. This module neither approves nor posts.
GoogleSearch and Codex web research are distinct executable contracts.
"""
import json,time
from urllib.parse import urlsplit
from workflow_control import CONTENT_WORKER,constrain,operation,run_stage
from workflow_routing import select,execute
from router_brain import RouterDecisionError


def valid_topics(topics):
    return bool(isinstance(topics,list) and topics and all(
        isinstance(t,dict) and all(isinstance(t.get(k),str) and t[k].strip()
        for k in ('title','summary','technical_impact','non_technical_impact'))
        and isinstance(t.get('sources'),list) and t['sources']
        and all(isinstance(u,str) and urlsplit(u).scheme=='https' and urlsplit(u).netloc for u in t['sources'])
        for t in topics))


def research(prompt,count,*,client,parse,worker=None,timeout=180):
    if type(count) is not int or not 1<=count<=12:
        raise ValueError('LinkedIn topic count must be between 1 and 12')
    offers=[{'id':'codex','provider':'openai','model':'gpt-6.1-sol',
             'capabilities':['web-search','read-only','observed-search-events']}]
    native=getattr(client,'_native',None) if client is not None else None
    if native is not None:
        offers.append({'id':'native','provider':'google','model':'gemini-2.5-flash',
                       'capabilities':['web-search','google-tools','grounding-metadata']})
    with operation(timeout,worker or CONTENT_WORKER.get()) as state:
        chosen,route=select('career.linkedin.research',constrain(offers,state.worker),
                           task=prompt,family='research',timeout=state.remaining(45))
        def dispatch():
            if chosen=='codex':
                from discovery.web_research import CodexWebSearchProvider
                provider=CodexWebSearchProvider(model=route['selected_model'],workflow='career.linkedin.research')
                result=provider._run_one(provider.resolve(),prompt,limit=count,timeout=state.remaining(),
                    prompt=prompt+'\nUse live web_search. In each JSON object also include url: the principal source URL. Never use private files or execute commands.')
                if result.get('error') or not result.get('web_search_observed'):
                    raise RouterDecisionError('linkedin_research_search_not_verified')
                topics=result.get('results') or []
                for topic in topics:
                    # The adapter proves a search event; the existing article-cache
                    # and claim gate subsequently check actual source content.
                    if topic.get('url') not in (topic.get('sources') or []):
                        raise RouterDecisionError('linkedin_research_source_mismatch')
                return topics[:count]
            from google.genai import types
            response=native.models.generate_content(model=route['selected_model'],contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_modalities=['TEXT'],http_options=types.HttpOptions(timeout=int(state.remaining()*1000),retry_options={'attempts':1})))
            candidates=getattr(response,'candidates',None) or []
            grounded_urls=set()
            for candidate in candidates:
                metadata=getattr(candidate,'grounding_metadata',None)
                for chunk in getattr(metadata,'grounding_chunks',None) or []:
                    url=getattr(getattr(chunk,'web',None),'uri',None)
                    if url:grounded_urls.add(url)
            topics=parse(str(response.text or ''),count)
            if not grounded_urls or any(not set(t.get('sources') or [])<=grounded_urls for t in topics):
                raise RouterDecisionError('linkedin_research_grounding_not_verified')
            return topics
        topics,receipt=run_stage('career.linkedin','research',{'prompt':prompt,'count':count},
            lambda:execute('career.linkedin.research',route,dispatch),valid_topics)
        return [dict(t,research_receipt=receipt) for t in topics]
