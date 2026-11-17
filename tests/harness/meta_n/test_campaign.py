import importlib.util
from pathlib import Path
import json
import pytest

spec = importlib.util.spec_from_file_location('campaign', Path(__file__).resolve().parents[3] / 'scripts/meta_n/campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def test_protocol_frozen_and_disjoint(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    p = campaign.freeze()
    ids = [t['id'] for split in ('G', 'D', 'T') for t in p[split]]
    hashes = [t['problem_hash'] for split in ('G', 'D', 'T') for t in p[split]]
    assert len(set(ids)) == len(ids) == 22
    assert len(set(hashes)) == 22
    assert p == campaign.freeze()
    data = json.loads((tmp_path/'protocol.json').read_text())
    data['D'][0]['answer'] = 'tampered'
    (tmp_path/'protocol.json').write_text(json.dumps(data))
    with pytest.raises(AssertionError):
        campaign.freeze()


def test_selection_tie_prefers_shared_a_and_does_not_test(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    p = campaign.freeze()
    for name in ('A', 'B', 'C'):
        campaign.save(tmp_path/'strategies'/f'{name}.json', {'injection_hash': name})
    rows = {n: [{'correct': True}] * len(p['D']) for n in ('A', 'B', 'AC')}
    selected = campaign.select(p, rows)
    assert selected['independent']['winner'] == selected['recursive']['winner'] == 'A'
    assert selected['test_executed'] is False
    rows['B'][0] = {'correct': False}
    with pytest.raises(ValueError):
        campaign.select(p, rows)


def test_only_pre_request_budget_refusal_can_be_resumed(tmp_path):
    path = tmp_path/'run.jsonl'
    refused = {'task_id':'x','score_status':'runtime_error','rationale':'Branch token budget exceeded',
               'token_usage':{},'request_messages':[]}
    scored = {'task_id':'x','score_status':'valid_scored','correct':False}
    path.write_text(json.dumps(refused)+'\n'+json.dumps(scored)+'\n')
    assert campaign.read_rows(path) == [scored]
    path.write_text(json.dumps(scored)+'\n'+json.dumps({**scored,'correct':True})+'\n')
    with pytest.raises(ValueError):
        campaign.read_rows(path)
