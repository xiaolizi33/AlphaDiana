import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import pytest
from alphadiana.benchmarks.math500.benchmark import Math500Benchmark
from alphadiana.scorer.math_verify_scorer import MathVerifyScorer
from alphadiana.benchmarks.base import BenchmarkTask
from alphadiana.harness.base import AgentResponse

scripts=Path(__file__).resolve().parents[3]/'scripts/meta_n'
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('freeze_math500',scripts/'freeze_math500.py')
freeze=importlib.util.module_from_spec(spec);spec.loader.exec_module(freeze)


def test_snapshot_allowlist_and_checksum(tmp_path):
    row={'unique_id':'x','problem':'Compute six times seven','answer':'42',
         'solution':'PRIVATE_SOLUTION','subject':'Algebra','level':1}
    data=(json.dumps(row)+'\n').encode();path=tmp_path/'data.jsonl';path.write_bytes(data)
    cfg={'snapshot':str(path),'sha256':hashlib.sha256(data).hexdigest(),'ids':['x']}
    task=Math500Benchmark().load_tasks(cfg)[0]
    assert task.ground_truth=='42'
    assert 'PRIVATE_SOLUTION' not in str(task.metadata) and 'answer' not in task.metadata
    with pytest.raises(ValueError):
        Math500Benchmark().load_tasks({**cfg,'sha256':'wrong'})
    with pytest.raises(ValueError):
        Math500Benchmark().load_tasks({**cfg,'ids':['x','x']})


@pytest.mark.parametrize('gold,pred,correct',[(r'\frac14',r'\frac{1}{4}',True),
    (r'\sqrt{12}',r'2\sqrt{3}',True),('(3,4)','(4,3)',False),('42','',False)])
def test_symbolic_scoring(gold,pred,correct):
    result=MathVerifyScorer().score(BenchmarkTask('t','',gold),AgentResponse(answer=pred))
    assert result.correct is correct
    if pred:
        assert result.metadata['method']=='math_verify'


def test_stratified_split_reproducible_disjoint():
    pool=[{'unique_id':str(n),'subject':str(n%3),'level':n%2} for n in range(100)]
    a,rest=freeze.stratified_take(pool,17,random.Random(9))
    b,_=freeze.stratified_take(pool,17,random.Random(9))
    assert a==b and len(a)==17 and len(rest)==83
    assert not {r['unique_id'] for r in a}&{r['unique_id'] for r in rest}
