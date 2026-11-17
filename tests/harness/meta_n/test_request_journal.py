import asyncio,json
from types import SimpleNamespace
import pytest
from alphadiana.harness.meta_n.client import SolverClient

def test_halt_rejection_is_finalized_and_preserves_original_reason(tmp_path):
    halt=tmp_path/'halt.json';halt.write_text('original provider error')
    client=SolverClient.__new__(SolverClient);client.config={'halt_file':str(halt),'request_log_dir':str(tmp_path/'requests')}
    with pytest.raises(RuntimeError,match='audit required'):asyncio.run(client.complete([]))
    row=json.loads(next((tmp_path/'requests').glob('*.json')).read_text())
    assert row['status']=='failed' and row['request_sent'] is False
    assert halt.read_text()=='original provider error'

def test_missing_usage_keeps_raw_response_and_reservation(tmp_path,monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','offline-test')
    cfg={'api_base':'https://example.invalid','model':'fake','max_tokens':1,'budget_ledger':str(tmp_path/'ledger'),
         'request_log_dir':str(tmp_path/'requests'),'pilot_cap_cny':1}
    client=SolverClient(cfg)
    class Response:
        usage=None
        def model_dump(self):return {'id':'paid-response','choices':[{'finish_reason':'stop'}]}
    async def fake(**kwargs):return Response()
    client.client.chat.completions.create=fake
    async def run():
        try:
            with pytest.raises(RuntimeError,match='usage'):await client.complete([])
        finally:await client.close()
    asyncio.run(run())
    row=json.loads(next((tmp_path/'requests').glob('*.json')).read_text())
    assert row['response']['id']=='paid-response' and row['request_sent'] is True and row['reserved_cny']>0
