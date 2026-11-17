import asyncio
import pytest
from alphadiana.harness.meta_n.executor import execute
from alphadiana.harness.meta_n.agent import MetaNAgent
from alphadiana.benchmarks.base import BenchmarkTask
from alphadiana.scorer.numeric import NumericScorer


def test_return_stdout_and_failure():
    assert execute('def solve():\n print("debug")\n return 42')["answer"] == "42"
    assert execute('def solve():\n print(42)')["answer"] == "42"
    result = execute('def solve():\n print(42)\n raise ValueError("bad")')
    assert result["exit_code"] != 0 and result["answer"] == ""
    assert execute('def solve():\n while True: pass', timeout=0.2)["timed_out"]


def test_sandbox_blocks_secrets_and_network(tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("SECRET")
    assert execute(f'def solve():\n return open({str(secret)!r}).read()')["exit_code"] != 0
    assert execute('import socket\ndef solve():\n socket.socket().connect(("1.1.1.1", 443))')["exit_code"] != 0
    assert execute('import os\ndef solve():\n return os.environ.get("DEEPSEEK_API_KEY", "absent")')["answer"] == "absent"


def test_official_solver_no_gold_and_usage(monkeypatch):
    from alphadiana.harness.meta_n import client
    class Fake:
        def __init__(self, config):
            pass
        async def complete(self, messages, **kwargs):
            assert "GOLD_SENTINEL" not in str(messages)
            assert "PRIVATE_METADATA" not in str(messages)
            self.messages = messages
            self.usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            self.reserve = 0
            self.response = {"model": "fake", "choices": [{"finish_reason": "stop"}]}
            return "```python\ndef solve():\n return 42\n```", 30
        async def close(self):
            pass
    monkeypatch.setattr(client, "SolverClient", Fake)
    agent = MetaNAgent()
    agent.setup({"max_tokens": 100})
    task = BenchmarkTask("test", "Compute six times seven.", "GOLD_SENTINEL", {"gold": "PRIVATE_METADATA"})
    response = agent.solve(task)
    assert response.answer == "42" and response.token_usage["total_tokens"] == 30
    task.ground_truth = "42"
    assert NumericScorer().score(task, response).correct
    with pytest.raises(FileNotFoundError):
        agent.setup({"strategy_chain": ["A"], "max_tokens": 100})


def test_budget_survives_new_clients_and_stops_before_request(tmp_path, monkeypatch):
    from alphadiana.harness.meta_n.client import SolverClient
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only")
    cfg = {"api_base": "https://example.invalid", "model": "fake", "max_tokens": 1,
           "budget_ledger": str(tmp_path / "ledger"), "pilot_cap_cny": 0.004}
    async def run():
        first = SolverClient(cfg)
        async def failed_request(**kwargs):
            raise ConnectionError("Ambiguous request outcome")
        first.client.chat.completions.create = failed_request
        try:
            with pytest.raises(ConnectionError):
                await first.complete([{"role": "user", "content": "hi"}])
        finally:
            await first.close()
        second = SolverClient(cfg)
        try:
            with pytest.raises(RuntimeError, match="Budget reservation refused"):
                await second.complete([{"role": "user", "content": "hi"}])
        finally:
            await second.close()
    asyncio.run(run())
