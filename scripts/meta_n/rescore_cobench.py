"""Repair scorer infrastructure errors using saved programs, without model calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import cobench_corrected as campaign
from alphadiana.harness.meta_n.co_bench import COBenchScorer
from alphadiana.harness.meta_n.layers import digest

def main():
    p=json.loads((campaign.ROOT/'protocol.json').read_text())
    for file in (campaign.ROOT/'results').glob('*.jsonl'):
        for row in map(json.loads,file.read_text().splitlines()):
            if row['score_status']=='valid_scored':continue
            if row.get('error',{}).get('error_type')!='PermissionError':raise RuntimeError('Unexpected failure; audit first')
            path=campaign.ROOT/'score_repairs'/file.stem/(row['task_id']+'.json')
            if path.exists():continue
            scorer=COBenchScorer();scorer.setup(campaign.score_config(p,file.stem.split('_')[1]))
            score=scorer.score(SimpleNamespace(task_id=row['task_id']),SimpleNamespace(answer=row['predicted'],finish_reason=row['finish_reason']))
            record={'original_row_hash':digest(row),'method':'saved_program_rescore_no_model_call','score':score.score,'correct':score.correct,'rationale':score.rationale,'score_metadata':score.metadata}
            campaign.core.save(path,record);print(file.name,row['task_id'],score.score)
if __name__=='__main__':main()
