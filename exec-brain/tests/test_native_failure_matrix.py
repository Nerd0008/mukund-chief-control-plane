import json
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import native_router_plugin as plugin
import workflow_routing as wr
from router_brain import RouterBrain
from hermes_cli import middleware, plugins


class ProviderError(Exception):
    def __init__(self, status, body=None, headers=None):
        super().__init__('synthetic provider refusal PRIVATE_SENTINEL')
        self.status_code=status
        self.body=body or {'reason':'rate_limited','retry_after':13}
        self.response=NS(headers=headers or {'Retry-After':'13'})


@pytest.fixture(autouse=True)
def offline(tmp_path,monkeypatch):
    wr._cache.clear()
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')
    manager=NS(_middleware={'llm_execution':[plugin.llm_execution]},_report_hook_failure=lambda *a,**kw:None)
    monkeypatch.setattr(plugins,'_delivery_manager',lambda:manager)


@pytest.mark.parametrize('status',[400,401,402,403,404,408,409,413,422,429,500,502,503,504])
def test_host_gets_identical_provider_exception_and_retry_metadata(status):
    error=ProviderError(status)
    def fail(request):raise error
    with patch.object(plugin,'select',return_value=('native',{'workflow':'fixture','selected_provider':'p','selected_model':'m'})):
        with pytest.raises(ProviderError) as caught:
            middleware.run_llm_execution_middleware({'messages':[]},fail,provider='p',model='m')
    assert caught.value is error
    assert caught.value.body['retry_after']==13
    assert caught.value.response.headers['Retry-After']=='13'


def test_wrapped_rate_limit_is_classified_without_losing_status():
    error=ProviderError(429)
    wrapped=middleware._DownstreamExecutionError(middleware._DownstreamExecutionError(error))
    assert wr.failure_code(wrapped)=='provider_rate_limit'


def test_failed_authorization_is_not_reused_from_selection_cache():
    calls=[]
    class Brain:
        def rank(self,candidates,**kwargs):calls.append(1);return candidates,{}
    offers=[wr.native_offer('p','m')]
    with patch.object(RouterBrain,'configured',return_value=Brain()):
        _,route=wr.select('fixture',offers,task='SYNTHETIC')
        def fail():raise ProviderError(429)
        with pytest.raises(ProviderError):wr.execute('fixture',route,fail)
        from router_brain import RouterDecisionError
        with pytest.raises(RouterDecisionError,match='no_healthy_compatible_worker'):
            wr.select('fixture',offers,task='SYNTHETIC')
    assert len(calls)==1


def test_receipts_do_not_contain_provider_body_or_exception_text(tmp_path):
    error=ProviderError(429,{'reason':'rate_limited','retry_after':13,'secret':'PRIVATE_SENTINEL'})
    def fail():raise error
    with pytest.raises(ProviderError):wr.execute('fixture',{},fail)
    records=''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'receipts').glob('*.json'))
    assert 'PRIVATE_SENTINEL' not in records
    assert 'provider_rate_limit' in records
