import importlib.util
from pathlib import Path
import sys
import pytest

scripts=Path(__file__).resolve().parents[3]/'scripts/meta_n'
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('report_formal',scripts/'report_formal.py')
report=importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_paired_direction_and_extreme_interval():
    base=[{'task_id':str(i),'correct':False} for i in range(3)]
    method=[{**r,'correct':True} for r in base]
    result=report.paired(base,list(reversed(method)))
    assert result['fixed']==['0','1','2'] and result['regressed']==[]
    assert result['delta_accuracy']==1
    assert result['paired_bootstrap_95_percentile']==[1,1]
    assert result['exact_mcnemar_two_sided_p']==.25
    assert report.paired(method,method)['exact_mcnemar_two_sided_p']==1
    with pytest.raises(ValueError): report.paired(base,method[:-1])
