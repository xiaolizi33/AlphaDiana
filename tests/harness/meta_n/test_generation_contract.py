"""Exercise the actual Omega template branch without a provider request."""
import asyncio
import importlib.util
import json
from pathlib import Path
import pytest

scripts=Path(__file__).resolve().parents[3]/'scripts/meta_n'
spec=importlib.util.spec_from_file_location('generation_contract_campaign',scripts/'campaign.py')
campaign=importlib.util.module_from_spec(spec);spec.loader.exec_module(campaign)

def test_recursive_generator_enters_official_meta_branch(tmp_path,monkeypatch):
    from alphadiana.harness.meta_n import client
    requests=[]
    class FakeClient:
        def __init__(self,config):pass
        async def complete(self,messages,**kwargs):
            self.messages=messages;requests.append(messages)
            self.response={'model':'offline','choices':[{'finish_reason':'stop'}]}
            self.usage={'total_tokens':1};self.reserve=0
            return '```pre_process\nadditional_context="check"\n```',1
        async def close(self):pass
    monkeypatch.setattr(client,'SolverClient',FakeClient)
    monkeypatch.setattr(campaign,'ROOT',tmp_path)
    def row(score):
        return {'task_id':'t','run_id':'G','trajectory':[{}],'metadata':{'execution':{'exit_code':0},'executed_script':'def solve(): return 42'},
                'raw_output':'visible output','correct':score>0,'score':score,'rationale':'feedback'}
    protocol={'G':[{'id':'t','problem':'Compute 6*7'}],'seed':42,'hash':'test'}
    a=asyncio.run(campaign.generate(protocol,'A',[],[row(0)],[]))
    c=asyncio.run(campaign.generate(protocol,'C',['A'],[row(1)],[],baseline_rows=[row(0)]))
    assert a['upstream_depth']==2 and c['upstream_depth']==3
    assert 'higher-order meta-layer (depth 3)' in requests[1][0]['content']
    assert 'higher-order meta-layer' not in requests[0][0]['content']
    assert c['baseline_rows_hash']==campaign.digest([row(0)])
    with pytest.raises(ValueError,match='baseline'):
        asyncio.run(campaign.generate(protocol,'D',['A'],[row(1)],[]))
