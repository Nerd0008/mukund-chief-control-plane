import pathlib,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from hermes_cover_tool import cover_fact_result

def gate(value='google workspace',**changes):return dict({'available':True,'exit_code':1,'verdict':'block','unsupportedFacts':[{'kind':'tool','value':value}],'invented':[],'forbidden':[]},**changes)

@pytest.mark.parametrize('text',[
 'I do not yet have professional experience supporting a Mac fleet or using Jamf, Google Workspace and Slack admin consoles.',
 'I have no professional experience with Google Workspace.',
 "I haven't worked with Google Workspace.",
])
def test_explicit_negative_is_not_skill_claim(text):
 result=cover_fact_result(gate(),text)
 assert result['exit_code']==0 and result['unsupportedFacts']==[]

@pytest.mark.parametrize('text',[
 'I manage Google Workspace.',
 'I have professional experience using Google Workspace.',
 'I have not used Slack, but I manage Google Workspace.',
 'I have not used Slack. I manage Google Workspace.',
 'I have not used Slack and I manage Google Workspace.',
 'I have not used Slack and manage Google Workspace.',
 'It is not true that I have not used Google Workspace.',
 'I have not used Google Workspace. I administer Google Workspace.',
])
def test_positive_or_ambiguous_claim_still_blocks(text):assert cover_fact_result(gate(),text)['exit_code']==1

def test_unknown_and_forbidden_claims_still_block():
 result=cover_fact_result(gate(invented=[{'kind':'achievement','value':'unknown'}]),'I have not used Google Workspace.')
 assert result['exit_code']==1 and result['invented']
 assert cover_fact_result(gate(available=False),'I have not used Google Workspace.')['exit_code']==1

def test_actual_rejected_tool_list_is_negative():
 text='I do not yet have professional experience supporting a Mac fleet or using Jamf or other endpoint management tools, Google Workspace and Slack admin consoles, or formal ticketing systems such as ServiceNow, Zendesk or Jira.'
 source=gate();source['unsupportedFacts']=[{'kind':'tool','value':v} for v in ('google workspace','slack admin consoles','zendesk or jira')]
 result=cover_fact_result(source,text)
 assert result['exit_code']==0 and len(source['unsupportedFacts'])==3
