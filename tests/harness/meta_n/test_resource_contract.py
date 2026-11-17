import pytest
from alphadiana.harness.meta_n.resource_contract import ResourceContract

def test_resource_limits_have_consistent_model_and_scorer_views():
    resource=ResourceContract(instance_timeout_seconds=7,helper_budget_seconds=3)
    assert 'after 7 seconds wall time' in resource.prompt()
    assert 'at most 3 seconds' in resource.prompt()
    assert resource.scorer_config()['instance_timeout']==7

def test_helper_must_leave_execution_headroom():
    with pytest.raises(ValueError):ResourceContract(instance_timeout_seconds=3,helper_budget_seconds=4)

@pytest.mark.parametrize("cleanup_permission_error",[False,True])
def test_scorer_worker_uses_configured_timeout(monkeypatch,tmp_path,cleanup_permission_error):
    from pathlib import Path
    from types import SimpleNamespace
    import alphadiana.harness.meta_n.co_bench as module
    data=tmp_path/'test';data.mkdir();(data/'config.py').write_text('def load_data(path): return [{}]*100\ndef get_dev(): return {"case.txt":[0]}\n');(data/'case.txt').write_text('official-fixture')
    captured=[];waits=[]
    class Process:
        pid=999999;returncode=0
        def __init__(self,args,**kwargs):
            root=Path(kwargs['cwd']);captured.append((root/'worker.py').read_text())
            (root/'result.json').write_text('{"dev_score":0.5,"dev_feedback":"test"}')
        def wait(self,**kwargs):waits.append(kwargs.get("timeout",0));return 0
        def poll(self):return 0
    monkeypatch.setattr(module.subprocess,'Popen',Process)
    def cleanup(*args):
        if cleanup_permission_error:raise PermissionError('completed process group')
    monkeypatch.setattr(module.os,'killpg',cleanup)
    result=module.evaluate_program('def solve(**kwargs): return {}','test',{
        'data_dir':str(tmp_path),'eval_split':'dev','instance_timeout':7})
    assert 'timeout=7' in captured[0] and result['score']==0.5
    assert max(waits)>=960  # 100 instances must each retain their allowed budget
