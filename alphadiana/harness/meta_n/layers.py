"""Official MetaLayer nesting; generated pre_process runs in an isolated worker."""
import json
from pathlib import Path
import hashlib
from meta_n.core.meta_layer import InjectedCode, MetaLayer, merge_code_libraries
from meta_n.core.code_library import SandboxMarker
from .executor import execute


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_chain(paths):
    result = []
    for path in paths:
        record = json.loads(Path(path).read_text())
        code = record["injection"]
        if record["injection_hash"] != digest(code):
            raise ValueError("Strategy artifact hash mismatch")
        ic = InjectedCode.model_validate(code)
        if ic.task_solution_map or ic.code_library_bash:
            raise ValueError("Math harness accepts Python strategy code only")
        result.append(ic)
    return result


class IsolatedMetaLayer(MetaLayer):
    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = events

    def _run_pre_process(self, task, outer_context=""):
        payload = json.dumps({"injection": self.injected_code.model_dump(),
                              "task": task.model_dump(), "outer_context": outer_context})
        script = '''import json
from meta_n.core.meta_layer import InjectedCode, TaskDescription, run_pre_process
def solve():
    data = json.loads(%r)
    ran, context = run_pre_process([InjectedCode.model_validate(data["injection"])], TaskDescription.model_validate(data["task"]), outer_context=data["outer_context"], pre_process_timeout=2)
    return json.dumps({"ran": ran, "context": context})
''' % payload
        output = execute(script, timeout=5, runtime=True)
        if output["exit_code"] != 0:
            raise RuntimeError("Isolated pre_process failed: " + output["stderr"])
        result = json.loads(output["answer"])
        self.events.append({"depth": self.depth, "outer_context": outer_context, **result})
        return result["context"]


def wrap_solver(solver, injections, events):
    py, bash = merge_code_libraries(injections)
    for index, injection in enumerate(injections):
        # Stage merged helpers once, at the outermost layer. Later layers win.
        outermost = index == len(injections) - 1
        solver = IsolatedMetaLayer(
            depth=index + 2, injected_code=injection, inner_solver=solver,
            executor=SandboxMarker(), merged_code_library=py if outermost else {},
            merged_code_library_bash={}, max_retries=0, events=events,
        )
    return solver
