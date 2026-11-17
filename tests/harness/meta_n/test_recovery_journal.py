import importlib.util
import json
import pytest
from pathlib import Path
import sys
from types import SimpleNamespace

@pytest.mark.parametrize("script",["recursive_ablation.py","recursive_ablation_16k.py"])
def test_truncated_multiline_problem_matches_unescaped_messages(tmp_path,monkeypatch,script):
    scripts=Path(__file__).resolve().parents[3]/'scripts/meta_n'
    monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('ablation_recovery_test',scripts/script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    record={'request_id':'original','messages':[{'content':'prefix\nfirst line\nsecond line\nsuffix'}],
            'response':{'choices':[{'finish_reason':'length'}]}}
    (tmp_path/'request.json').write_text(json.dumps(record))
    found=module.retained_truncations(SimpleNamespace(description='first line\nsecond line'),tmp_path)
    assert len(found)==1 and found[0]['request_id']=='original'
