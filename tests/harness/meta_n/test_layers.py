import asyncio
from meta_n.core.meta_layer import InjectedCode, TaskDescription
from alphadiana.harness.meta_n.layers import wrap_solver
from alphadiana.harness.meta_n.executor import execute


def test_official_nested_order_outer_context_and_helper_override():
    events = []
    seen = []
    class Base:
        async def solve(self, task, additional_context=""):
            seen.append(additional_context)
            return 'def solve(): return helper()', 'raw', 3
    a = InjectedCode(pre_process='additional_context = "A sees " + outer_context',
                     code_library={"helper": 'def helper(): return 1'})
    c = InjectedCode(pre_process='additional_context = "C advice"',
                     code_library={"helper": 'def helper(): return 2'})
    snapshot = a.model_dump()
    wrapped = wrap_solver(Base(), [a, c], events)
    code, _, tokens = asyncio.run(wrapped.solve(TaskDescription(task_id="t", description="test")))
    assert [e["depth"] for e in events] == [3, 2]
    assert "C advice" in events[1]["outer_context"]
    assert "A sees C advice" in seen[0]
    assert execute(code)["answer"] == "2"
    assert a.model_dump() == snapshot and tokens == 3
