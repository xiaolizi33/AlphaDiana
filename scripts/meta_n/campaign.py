"""Steps 2/3: immutable pilot splits → official Omega → Diana runs → dev selection."""
import argparse
import asyncio
from dataclasses import asdict
import inspect
import json
import math
import os
from pathlib import Path
import random
import subprocess

from alphadiana.harness.meta_n.layers import digest, load_chain

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO.parent / "experiments/recursive_pilot"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"Refusing to overwrite frozen artifact {path}")
        return
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text)
    temp.replace(path)


def freeze():
    path = ROOT / "protocol.json"
    if path.exists():
        record = json.loads(path.read_text())
        expected = record.pop("hash")
        assert digest(record) == expected, "Protocol hash mismatch"
        record["hash"] = expected
        return record
    # Synthetic numerical math suite: fixed before any model outputs are seen.
    tasks = []
    for n in range(8, 30):
        kind = n % 6
        if kind == 0:
            text = f"How many length-{n} binary strings contain no adjacent ones?"
            a, b = 1, 2
            for _ in range(n):
                a, b = b, a + b
            answer = a
        elif kind == 1:
            text = f"Find the remainder of 7^{n * 11} upon division by 97."
            answer = pow(7, n * 11, 97)
        elif kind == 2:
            text = f"How many nonnegative integer triples (x,y,z) satisfy x+y+z={n}, x>=2 and y>=3?"
            answer = math.comb(n - 5 + 2, 2)
        elif kind == 3:
            text = f"Compute the sum of gcd(k,{n}) for all integers k from 1 through {n}."
            answer = sum(math.gcd(k, n) for k in range(1, n+1))
        elif kind == 4:
            text = f"How many subsets of {{1,2,...,{n}}} have a sum divisible by 5? Include the empty subset."
            dp = [1, 0, 0, 0, 0]
            for k in range(1, n+1):
                dp = [dp[r] + dp[(r-k) % 5] for r in range(5)]
            answer = dp[0]
        else:
            text = f"How many integers between 1 and {n * 100}, inclusive, are divisible by 3 or 5 but not both?"
            top = n * 100
            answer = top//3 + top//5 - 2*(top//15)
        tasks.append({"id": f"synthetic_{n}", "problem": text, "answer": str(answer),
                      "problem_hash": digest(text)})
    random.Random(20261114).shuffle(tasks)
    record = {"purpose": "engineering_pilot_not_formal_benchmark", "seed": 20261114,
              "G": tasks[:6], "D": tasks[6:14], "T": tasks[14:],
              "tie_rule": "accuracy, shallower depth, A first",
              "model": "deepseek-flash", "solver_max_tokens": 2048, "omega_max_tokens": 4096,
              "omega_input_bound": 80000, "solver_input_bound": 16000,
              "branch_search_token_bound": 300000, "branch_search_cny_reserve_cap": 5,
              "invalid_strategy": "no repair; retain artifact and use parent for selection",
              "test_policy": "T frozen, not executed in steps 2/3",
              "upstream_meta_n": subprocess.check_output(['git','-C',str(REPO.parent/'meta-n'),'rev-parse','HEAD'], text=True).strip()}
    record["hash"] = digest(record)
    save(path, record)
    return record


def client_config(branches, omega=False, protocol=None):
    if protocol and "splits" in protocol:
        prefix = "omega" if omega else "solver"
        return {"model": protocol["model"], "api_base": "https://api.deepseek.com",
                "max_tokens": protocol[f"{prefix}_max_tokens"],
                "input_token_bound": protocol[f"{prefix}_input_bound"],
                "budget_ledger": str(REPO.parent / "experiments/budget_reservations.jsonl"),
                "budget_scope": "math500_formal",
                "pilot_cap_cny": protocol["formal_scope_cny_reservation_cap"],
                "budget_branches": branches,
                "branch_token_cap": protocol["branch_search_token_reservation_cap"],
                "branch_cny_cap": protocol["branch_search_cny_reservation_cap"],
                "execution_timeout": protocol["execution_timeout"],
                "answer_contract": protocol["answer_contract"],
                "halt_file": str(REPO.parent / "experiments/math500_formal/request_halted.json")}
    return {"model": "deepseek-flash", "api_base": "https://api.deepseek.com",
            "max_tokens": 4096 if omega else 2048,
            "input_token_bound": 80000 if omega else 16000,
            "budget_ledger": str(REPO.parent / "experiments/budget_reservations.jsonl"),
            "budget_scope": "step23", "pilot_cap_cny": 10,
            "budget_branches": branches, "execution_timeout": 5}


def read_rows(path):
    first = {}
    for row in map(json.loads, path.read_text().splitlines()):
        previous = first.get(row["task_id"])
        if previous is None:
            first[row["task_id"]] = row
        elif (previous.get("score_status") == "runtime_error"
              and previous.get("rationale") == "Branch token budget exceeded"
              and not previous.get("token_usage") and not previous.get("request_messages")):
            # Sole permitted retry: budget guard refused BEFORE a paid request.
            first[row["task_id"]] = row
        else:
            raise ValueError("Refusing duplicate model attempts")
    return list(first.values())


def diana_run(protocol, split, label, chain, branches):
    result_path = ROOT / "results" / f"{split}_{label}.jsonl"
    if result_path.exists():
        existing = read_rows(result_path)
        if len(existing) == len(protocol[split]) and all(r.get("score_status") == "valid_scored" for r in existing):
            return existing
    import yaml
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    from alphadiana.engine.runner import Runner
    paths = [str(ROOT / "strategies" / f"{name}.json") for name in chain]
    cfg = {"run_id": f"{split}_{label}", "agent": {"name": "meta_n", "version": "0.2.0",
           "config": {**client_config(branches), "strategy_chain": paths}},
           "benchmark": {"name": "custom", "config": {"problems": protocol[split]}},
           "scorer": {"name": "numeric", "config": {"tolerance": 1e-6}},
           "num_samples": 1, "max_concurrent": 1, "output_dir": str(ROOT / "results"),
           "metadata": {"protocol_hash": protocol["hash"], "split": split, "candidate": label}}
    config_path = ROOT / "configs" / f"{split}_{label}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    amendment = ROOT / "budget_extension.json"
    if amendment.exists():
        extension = json.loads(amendment.read_text())
        cfg["agent"]["config"]["branch_token_cap"] = extension["branch_token_cap"]
        cfg["metadata"]["budget_extension_hash"] = digest(extension)
        config_path = config_path.with_name(config_path.stem + "_supplemental.yaml")
    text = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    if config_path.exists() and config_path.read_text() != text:
        raise ValueError("Frozen run config changed")
    config_path.write_text(text)
    experiment = ExperimentConfig.from_yaml(str(config_path))
    errors = ConfigValidator().validate(experiment)
    if errors:
        raise ValueError(errors)
    runner = Runner(experiment)
    try:
        runner.setup()
        runner.run()
    finally:
        runner.teardown()
    path = ROOT / "results" / f"{split}_{label}.jsonl"
    rows = read_rows(path)
    if len(rows) != len(protocol[split]) or any(r.get("score_status") != "valid_scored" for r in rows):
        raise RuntimeError("Incomplete run; inspect failures before continuing")
    return rows


async def generate(protocol, name, parent, rows, branches, baseline_rows=None):
    from alphadiana.harness.meta_n.client import SolverClient
    from meta_n.core.omega import OmegaEngine
    from meta_n.core.meta_layer import Trace, TaskDescription
    from meta_n.core.solver import Layer1Solver
    from meta_n.utils.context_manager import ContextBudget
    target = ROOT / "strategies" / f"{name}.json"
    if target.exists():
        load_chain([target])
        return json.loads(target.read_text())
    attempt = ROOT / "strategies" / f"{name}.attempt.json"
    if attempt.exists():
        raise RuntimeError(f"Prior {name} attempt incomplete; no automatic paid regeneration")
    if parent and baseline_rows is None:
        raise ValueError('Recursive Omega requires the pre-parent baseline traces')
    baseline_rows = rows if baseline_rows is None else baseline_rows
    if {r['task_id'] for r in baseline_rows} != {r['task_id'] for r in rows}:
        raise ValueError('Baseline and current task IDs differ')
    traces = []
    for row in rows:
        tool = row["trajectory"][-1]
        execution = row["metadata"]["execution"]
        script = row["metadata"].get("executed_script")
        if script is None:
            if parent:
                raise ValueError("Missing executed strategy script")
            script = Layer1Solver.__new__(Layer1Solver)._extract_python_code(row["raw_output"])
        traces.append(Trace(task_id=row["task_id"], depth=len(parent)+1, script=script,
                            stdout=execution.get("stdout", ""), stderr=execution.get("stderr", ""),
                            exit_code=execution["exit_code"], success=bool(row["correct"]), score=row["score"],
                            reasoning=row["raw_output"], eval_feedback=row["rationale"]))
    tasks = [TaskDescription(task_id=t["id"], description=t["problem"],
                             metadata={"solution_language": "python"}) for t in protocol["G"]]
    chain = load_chain([ROOT/"strategies"/f"{p}.json" for p in parent])
    for index, ancestor in enumerate(parent):
        record = json.loads((ROOT/'strategies'/f'{ancestor}.json').read_text())
        if record.get('upstream_depth') != index + 2:
            raise ValueError('Legacy depth convention: retain historical artifacts and start a fresh protocol')
    source = inspect.getsource(Layer1Solver)
    solver_program = {"base_solver_source": source, "parent_injections": [ic.model_dump() for ic in chain],
                      "execution_contract": protocol.get("answer_contract", "solve() has no arguments, returns final numeric answer; no llm helper")}
    client = SolverClient(client_config(branches, omega=True, protocol=protocol))
    original = client.complete
    async def complete(messages, **kwargs):
        # Explicit source attachment at all depths; preserve official Omega template.
        augmented = [{**m, "content": "## Actual solver program and installed chain\n" +
                      json.dumps(solver_program, ensure_ascii=False) + "\n\n" + m["content"]} for m in messages]
        if protocol.get('generation_directive'):
            augmented = [{**m, 'content': m['content'] + '\n\n## Fixed-depth experiment directive\n' +
                          protocol['generation_directive']} for m in augmented]
        save(ROOT/"strategies"/f"{name}.request.json", augmented)
        result = await original(augmented, **kwargs)
        save(ROOT/"strategies"/f"{name}.response.json", {"response": client.response, "usage": client.usage})
        return result
    client.complete = complete
    save(attempt, {"name": name, "parent": parent, "source_run_ids": sorted({r["run_id"] for r in rows}),
                   "source_rows_hash": digest(rows), "protocol_hash": protocol["hash"]})
    try:
        engine = OmegaEngine(client, context_budget=ContextBudget(max_tokens=24000))
        engine.context_manager.rng = random.Random(protocol["seed"])
        injection, tokens = await engine.generate(
            traces, chain, tasks, depth=len(parent)+2,
            previous_scores={r['task_id']:r['score'] for r in baseline_rows},
            current_scores={r['task_id']:r['score'] for r in rows},
            temperature=0.7, solver_language="python")
        valid = client.response["choices"][0]["finish_reason"] == "stop" and not injection.is_empty
        if injection.task_solution_map or injection.code_library_bash:
            valid = False
        record = {"name": name, "parent": parent, "protocol_hash": protocol["hash"],
                  "upstream_depth": len(parent)+2, "baseline_rows_hash": digest(baseline_rows),
                  "source_rows_hash": digest(rows), "solver_source_hash": digest(source),
                  "injection": injection.model_dump(), "injection_hash": digest(injection.model_dump()),
                  "request_messages": client.messages, "response_json": client.response,
                  "token_usage": client.usage, "reserved_cny": client.reserve, "valid": valid,
                  "tokens": tokens}
        save(target, record)
        return record
    finally:
        await client.close()


def select(protocol, rows):
    def choose(names):
        ranked = sorted(names, key=lambda n: (-sum(r["correct"] for r in rows[n]),
                                             2 if n == "AC" else 1, names.index(n)))
        winner = ranked[0]
        chain = ["A", "C"] if winner == "AC" else [winner]
        return {"winner": winner, "chain": chain,
                "chain_hashes": [json.loads((ROOT/"strategies"/f"{n}.json").read_text())["injection_hash"] for n in chain],
                "dev_correct": {n: sum(r["correct"] for r in rows[n]) for n in names},
                "dev_n": len(protocol["D"])}
    result = {"protocol_hash": protocol["hash"], "independent": choose(["A", "B"]),
              "recursive": choose(["A", "AC"]), "test_executed": False,
              "supplemental_budget": (ROOT/"budget_extension.json").exists(),
              "dev_results_hash": digest(rows)}
    save(ROOT/"selection.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["2", "3"], required=True)
    args = parser.parse_args()
    os.chdir(REPO)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        os.environ["DEEPSEEK_API_KEY"] = (REPO.parent/"apikey").read_text().strip().strip("\"'")
    p = freeze()
    both = ["independent", "recursive"]
    base = diana_run(p, "G", "base", [], both)
    a = asyncio.run(generate(p, "A", [], base, both))
    if not a["valid"]:
        raise RuntimeError("A invalid; stop this pilot without repair")
    ta = diana_run(p, "G", "A", ["A"], ["recursive"])
    c = asyncio.run(generate(p, "C", ["A"], ta, ["recursive"], baseline_rows=base))
    if c["valid"]:
        diana_run(p, "G", "AC", ["A", "C"], ["recursive"])
    if args.stage == "2":
        print("Step 2 complete", ROOT)
        return
    b = asyncio.run(generate(p, "B", [], base, ["independent"]))
    rows = {"A": diana_run(p, "D", "A", ["A"], both)}
    # Invalid output is retained and parent fallback uses the same A samples.
    rows["B"] = diana_run(p, "D", "B", ["B"], ["independent"]) if b["valid"] else rows["A"]
    rows["AC"] = diana_run(p, "D", "AC", ["A", "C"], ["recursive"]) if c["valid"] else rows["A"]
    print(json.dumps(select(p, rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
