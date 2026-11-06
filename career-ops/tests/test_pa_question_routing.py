import asyncio
from types import SimpleNamespace as NS
import pytest
import application_package_state as package
import application_package_flow as flow
import hermes_cv_compiler_guard as guard

QUESTION=('Tell us what inspired your application to join PA Consulting. You might refer to a position of responsibility, '
          'a project or work experience. Explain the circumstances and what you learned, why it motivated you to pursue digital consulting, '
          'and what attracts you to PA Consulting specifically. Maximum 250 words. ' * 2)

@pytest.mark.parametrize('message',[
 'wtf answer this question\n[The user sent an image~ Here is what I can see: '+QUESTION+']',
 'I need you to answer this application question for this PA consulting role',
 'Please draft an answer to this question',
 QUESTION+'\nanswer this question',
 QUESTION+' In your response, explain your motivation.',
])
def test_question_does_not_dispatch_documents_or_destroy_checkpoint(tmp_path,monkeypatch,message):
 monkeypatch.setattr(package,'ROOT',tmp_path/'packages')
 saved={'session_id':'fixture','cv_active':True,'request_id':'original','phase':'OWNER_INPUT_REQUIRED',
        'intake':{'jd':'A saved JD describing responsibilities and requirements. '*12}}
 package.save(saved);before=package.load('fixture')
 monkeypatch.setattr(flow,'dispatch',lambda state:pytest.fail('Question must not dispatch documents'))
 class Turn:
  async def _run_agent(self,message,context,history,*args,**kwargs):
   assert 'unless the owner requests CV only' not in context
   assert not guard.active_job()
   assert guard.pre_tool('career_cv_compile',{})['action']=='block'
   return {'final_response':'A direct answer','failed':False}
 class Media:
  async def send_document(self,*a,**k):pytest.fail('Unexpected delivery')
 guard.install_runtime(NS(_current_max_iterations=lambda:150),Turn,Media)
 result=asyncio.run(Turn()._run_agent(message,'',[],None,'fixture'))
 assert result['final_response']=='A direct answer'
 assert package.load('fixture')==before
