"""Build a code/trace case using generation-feedback data, clearly labelled."""
import json
import cobench_corrected as campaign
from alphadiana.harness.meta_n.layers import digest

def main():
    root=campaign.ROOT;task='common_due_date_scheduling'
    runs={name:next(r for r in campaign.read_rows(root/'results'/f'cobench_G_{name}.jsonl') if r['task_id']==task) for name in ['base','A','AC']}
    strategies={n:json.loads((root/'strategies'/f'{n}.json').read_text()) for n in ['A','C']}
    events=runs['AC']['metadata']['layer_events'];assert len(events)==2
    case={'split':'G','purpose':'mechanism illustration only; generation feedback is not held-out evidence',
          'task_id':task,'problem':runs['base']['problem'],
          'scores':{n:r['score'] for n,r in runs.items()},
          'code_and_visible_execution':{n:{'script':r['metadata']['executed_script'],'feedback':r['rationale'],'layer_events':r['metadata']['layer_events']} for n,r in runs.items()},
          'strategies':{n:{'injection':s['injection'],'hash':s['injection_hash'],'source_rows_hash':s['source_rows_hash']} for n,s in strategies.items()},
          'C_input_matches_G_A':strategies['C']['source_rows_hash']==digest(campaign.omega_rows(campaign.read_rows(root/'results/cobench_G_A.jsonl'))),
          'interpretation':'A lowered the generation-set score; A+C restored it. Layer events expose C→A context propagation. One observed recovery is not a causal attribution to a particular prompt or a test-generalization result.'}
    assert case['C_input_matches_G_A']
    (root/'recursive_case_study.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    print(case['scores'], 'C→A events',[(e['depth'],len(e['outer_context'])) for e in events])
if __name__=='__main__':main()
