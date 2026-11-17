"""Exclude one unintended repeated output; retain the original truncation as zero."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]/'experiments/deepseek_recursive_ablation'
def main():
    root=ROOT/'depth1';audit=ROOT/'recovery_audit';audit.mkdir(exist_ok=True)
    truncated='7e8953833e0a4f7583c567a47c75d428';extra='a96161acda434ed28b6db92cd96128aa'
    if (audit/'resolution.json').exists():print('Already audited; no calls.');return
    for name in ['draw_2.json','draw_2_common_due_date_scheduling.json']:
        shutil.copy2(root/name,audit/name)
    shutil.copy2(ROOT/'comparison.json',audit/'comparison_before.json')
    source=json.loads((root/'requests'/f'{truncated}.json').read_text())
    row={'task_id':'common_due_date_scheduling','script':'','raw_output':source['response']['choices'][0]['message']['content'],
         'tokens':source['usage']['total_tokens'],'score':0.,'feedback':'Original truncated draw retained as zero; unintended replacement excluded',
         'source_request_id':truncated}
    (root/'draw_2_common_due_date_scheduling.json').write_text(json.dumps(row,indent=2)+'\n')
    draw=json.loads((root/'draw_2.json').read_text());draw['rows']=[row if x['task_id']==row['task_id'] else x for x in draw['rows']]
    (root/'draw_2.json').write_text(json.dumps(draw,indent=2)+'\n')
    comparison=json.loads((ROOT/'comparison.json').read_text());comparison['depth1']['draw_means'][2]=sum(r['score'] for r in draw['rows'])/3
    # Best flat draw and both estimators are unchanged (draw 3 was stronger).
    comparison['recovery_audit']='recovery_audit/resolution.json'
    (ROOT/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    resolution={'issue':'Recovery matching compared raw multiline description against JSON-escaped messages and missed the retained truncation, causing one unintended repeat',
                'original_truncation_request':truncated,'excluded_extra_request':extra,'resolution':'original response scored zero; extra output excluded from selection and metrics but included in physical tokens and cost',
                'paid_requests_in_this_audit':0,'best_flat_estimators_changed':False,
                'original_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in audit.glob('*json')}}
    (audit/'resolution.json').write_text(json.dumps(resolution,indent=2)+'\n');print(json.dumps(resolution,indent=2))
if __name__=='__main__':main()
