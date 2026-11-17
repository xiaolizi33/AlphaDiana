"""Extract the first depth-3 candidate with a per-task gain, without cherry-picking best."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]/'experiments/deepseek_recursive_ablation_16k'
def main():
    archive=ROOT/'full/archive';index=json.loads((archive/'index.json').read_text());byid={c['candidate_id']:c for c in index['candidates']}
    pairs=[]
    for c in index['candidates']:
        if c['depth']<3:continue
        parent=byid[c['parent_id']]
        for task,score in c['per_task_scores'].items():
            if score>parent['per_task_scores'][task]+1e-9:pairs.append((c,parent,task));break
    if not pairs:raise RuntimeError('No depth-3 recovery case; preserve negative search result')
    child,parent,task=pairs[0]
    folder=archive/child['candidate_id'];previous=archive/parent['candidate_id']
    trace=json.loads((folder/'traces'/f'{task}.json').read_text());parent_trace=json.loads((previous/'traces'/f'{task}.json').read_text())
    injections={p.name:json.loads(p.read_text()) for p in sorted(folder.glob('injected_code_d*.json'))}
    program=trace['script'];calls=[]
    for node in ast.walk(ast.parse(program)):
        if isinstance(node,ast.Call):
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else None
            if name:calls.append(name)
    events=[json.loads(l) for l in (ROOT/'full/layer_events.jsonl').read_text().splitlines()]
    case={'selection_rule':'first archived depth>=3 candidate having any per-task gain over its parent; first such task in archive order',
          'split':'validation used during search; not held-out','child':child,'parent':parent,'task_id':task,
          'parent_trace':parent_trace,'child_trace':trace,'injections':injections,
          'outer_omega_request':(folder/'omega_prompt_d3.txt').read_text(),
          'outer_omega_visible_response':(folder/'omega_response_d3.txt').read_text(),
          'helper_call_expressions_in_program':sorted(set(calls)),
          'global_run_nonempty_outer_context_events':sum(bool(e['outer_context']) for e in events),
          'interpretation':'The outer layer replaces the same-name CDD helper after seeing the parent code and its score. The child program contains a helper call and earns a higher official score. Model-provided mathematical diagnosis is not independently proven; code-level or seed-controlled ablations would be needed for causal attribution.'}
    (ROOT/'recursive_case_study.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    print(child['candidate_id'],parent['candidate_id'],task,parent['per_task_scores'][task],child['per_task_scores'][task])
if __name__=='__main__':main()
