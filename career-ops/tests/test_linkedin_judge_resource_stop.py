from unittest.mock import patch
import linkedin_factcheck as fc


def test_router_resource_failure_stops_content_correction_loop():
    blocked={'runs':[],'responses':[{'error_type':'RouterDecisionError','error':'router_cli_rate_limited','retry_after_seconds':197}]}
    with patch.object(fc,'run_judge',return_value=blocked) as judge:
        result=fc.llm_verify_claims('Acme released a new tool.', 'Acme released a new tool.',api_key='synthetic',runs=3)
    assert judge.call_count==1
    assert result['complete'] is False and result['used'] is False
    assert result['operational_error']=='router_cli_rate_limited'
    assert result['retry_after_seconds']==197
    assert 'content is not rejected' in result['reason']
