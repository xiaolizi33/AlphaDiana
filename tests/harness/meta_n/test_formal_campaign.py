"""Formal protocol enforcement and safe resume behavior without API requests."""
import importlib.util
from pathlib import Path
import sys
import asyncio
import pytest

scripts = Path(__file__).resolve().parents[3]/'scripts/meta_n'
sys.path.insert(0,str(scripts))
spec = importlib.util.spec_from_file_location('formal_campaign', scripts/'formal_campaign.py')
formal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formal)


def test_formal_config_preserves_frozen_settings_and_gold_boundary(monkeypatch):
    fixtures=Path(__file__).resolve().parents[2]/'fixtures/meta_n'
    monkeypatch.setattr(formal,'ROOT',fixtures)
    monkeypatch.setattr(formal,'SNAPSHOT',fixtures/'snapshot.jsonl')
    p,tasks = formal.protocol()
    cfg = formal.config(p,'G','base',[],formal.BOTH)
    agent = cfg['agent']['config']
    assert agent['max_tokens'] == p['solver_max_tokens'] == 8192
    assert agent['budget_scope'] == 'math500_formal'
    assert agent['branch_token_cap'] == p['branch_search_token_reservation_cap']
    assert agent['branch_cny_cap'] == p['branch_search_cny_reservation_cap']
    assert agent['pilot_cap_cny'] == p['formal_scope_cny_reservation_cap']
    assert cfg['scorer']['name'] == 'math_verify'
    assert cfg['benchmark']['config']['ids'] == [t['id'] for t in tasks]
    assert all(set(t)=={'id','problem'} for t in tasks)
    omega = formal.core.client_config(formal.BOTH,omega=True,protocol=p)
    assert omega['max_tokens'] == p['omega_max_tokens']
    assert omega['input_token_bound'] == p['omega_input_bound']
    assert Path(agent['halt_file']).parent == fixtures
    assert Path(omega['halt_file']).name == 'request_halted.json'


def test_resume_rejects_failed_duplicate_or_foreign_results():
    row={'task_id':'a','score_status':'valid_scored'}
    formal.check_rows([row],['a','b'])
    for rows in ([row,row],[{**row,'task_id':'foreign'}],[{**row,'score_status':'runtime_error'}]):
        with pytest.raises((ValueError,RuntimeError)):
            formal.check_rows(rows,['a','b'])
    with pytest.raises(RuntimeError):
        formal.check_rows([row],['a','b'],complete=True)


def test_request_failure_blocks_later_paid_requests(tmp_path,monkeypatch):
    from alphadiana.harness.meta_n.client import SolverClient
    client=SolverClient.__new__(SolverClient)
    halt=tmp_path/'halt.json'
    client.config={'halt_file':str(halt)}
    calls=[]
    async def fail(*args,**kwargs):
        calls.append(1)
        raise RuntimeError('provider failure')
    monkeypatch.setattr(client,'_complete',fail)
    with pytest.raises(RuntimeError,match='provider failure'):
        asyncio.run(client.complete([]))
    with pytest.raises(RuntimeError,match='audit required'):
        asyncio.run(client.complete([]))
    assert len(calls)==1 and halt.exists()
