"""Meta-n solver and official strategy layers exposed as a Diana Agent."""
import asyncio
import time
from alphadiana.engine.components import register_agent
from alphadiana.harness.base import Agent, AgentResponse
from .executor import execute


@register_agent("meta_n")
class MetaNAgent(Agent):
    name = "meta_n"
    version = "0.1.0"

    def execute_script(self, script):
        return execute(script, self.config.get("execution_timeout", 5))

    def setup(self, config):
        from meta_n.core.solver import Layer1Solver
        self.config = dict(config)
        from .layers import load_chain
        self.injections = load_chain(config.get("strategy_chain", []))
        if config.get("max_tokens", 0) <= 0:
            raise ValueError("Set a positive max_tokens")
        self.solver_class = Layer1Solver

    def solve(self, task, sandbox=None):
        return asyncio.run(self._solve(task))

    async def _solve(self, task):
        from meta_n.core.meta_layer import TaskDescription
        from .client import SolverClient
        start = time.monotonic()
        # Explicit allowlist: neither gold nor BenchmarkTask.metadata crosses here.
        description = TaskDescription(
            task_id=task.task_id,
            description=task.problem + "\n" + self.config.get("answer_contract", "Implement solve() with no arguments. Return the final numeric answer, or print it. Use only standard-library computation; llm/llm_batch are unavailable."),
            metadata={"solution_language": "python"},
        )
        client = SolverClient(self.config)
        try:
            solver = self.solver_class(client, language="python")
            from .layers import wrap_solver
            events = []
            # MetaLayer calls solve(task, context) without a temperature argument.
            base = solver
            class FixedTemperature:
                async def solve(self, task, additional_context=""):
                    return await base.solve(task, additional_context, temperature=0)
            wrapped = wrap_solver(FixedTemperature(), self.injections, events)
            script, raw, tokens = await wrapped.solve(description)
            choice = client.response["choices"][0]
            if choice["finish_reason"] != "stop":
                result = {"answer": "", "exit_code": -1, "stderr": "Incomplete model output", "stdout": "", "timed_out": False}
            else:
                result = self.execute_script(script)
            return AgentResponse(
                answer=result["answer"] if result["exit_code"] == 0 else "",
                raw_output=raw, token_usage=client.usage,
                request_messages=client.messages, response_json=client.response,
                trajectory=[{"role": "user", "content": client.messages[0]["content"]},
                            {"role": "assistant", "content": raw},
                            {"role": "tool", "content": result, "script": script}],
                wall_time_sec=time.monotonic() - start,
                finish_reason="timeout" if result["timed_out"] else choice["finish_reason"],
                metadata={"executed_script": script, "strategy_depth": len(self.injections), "layer_events": events, "execution": result,
                          "model": client.response["model"], "reserved_cny": client.reserve,
                          "solver_tokens": tokens, "executor": "macos_sandbox"},
            )
        finally:
            await client.close()
