from types import SimpleNamespace
from alphadiana.harness.meta_n.co_bench import COBenchAgent, COBenchScorer

def test_program_is_not_called_as_numeric_solver():
    script='def solve(**kwargs):\n    return {"value": kwargs["value"]}'
    result=COBenchAgent().execute_script(script)
    assert result['answer']==script and result['exit_code']==0

def test_incomplete_program_not_evaluated(monkeypatch):
    scorer=COBenchScorer();scorer.setup({})
    def refuse(*args):raise AssertionError('must not execute truncated program')
    monkeypatch.setattr('alphadiana.harness.meta_n.co_bench.evaluate_program',refuse)
    result=scorer.score(None,SimpleNamespace(finish_reason='length',answer='partial'))
    assert result.score==0

def test_continuous_quality_preserved(monkeypatch):
    scorer=COBenchScorer();scorer.setup({'task_names':{'t':'task'}})
    monkeypatch.setattr('alphadiana.harness.meta_n.co_bench.evaluate_program',lambda *args:{'score':0.375,'feedback':'official normalized quality'})
    result=scorer.score(SimpleNamespace(task_id='t'),SimpleNamespace(finish_reason='stop',answer='script'))
    assert result.score==0.375 and result.correct
