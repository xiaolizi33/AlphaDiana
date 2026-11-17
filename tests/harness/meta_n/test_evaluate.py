import importlib.util
from pathlib import Path
import sys

scripts = Path(__file__).resolve().parents[3] / 'scripts/meta_n'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('evaluate_test', scripts/'evaluate_test.py')
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


def test_paired_counts_by_task_id():
    base = {key:{'correct':value} for key,value in [('a',True),('b',False),('c',True),('d',False)]}
    method = {key:{'correct':value} for key,value in [('d',False),('c',False),('b',True),('a',True)]}
    assert evaluate.paired(base,method) == {'fixed':['b'],'regressed':['c'],
                                          'both_correct':['a'],'both_wrong':['d']}
