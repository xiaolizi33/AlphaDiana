"""Exercise the real orchestration loop without API requests or generated execution."""
import asyncio,json,tempfile
from pathlib import Path
import recursive_ablation as ab
from meta_n.integrations.benchmark import EvalResult

class FakeClient:
    def __init__(self,config):self.config=config;self.cumulative_usage={}
    async def complete(self,*args,**kwargs):
        return ('```pre_process\nadditional_context = "offline strategy"\n```\n```python\ndef solve(**kwargs):\n    return {}\n```',10)
    async def close(self):pass
class FakeAdapter(ab.SafeAdapter):
    async def evaluate(self,task,solution):return EvalResult(success=True,score=0.5,raw_score=0.5,feedback='offline evaluator')
async def main():
    p,adapter,tasks=ab.protocol()
    with tempfile.TemporaryDirectory() as directory:
        ab.ROOT=Path(directory);ab.ContractClient=FakeClient
        adapter=FakeAdapter(str(ab.DATA),task_names=ab.TASK_NAMES)
        full=await ab.run_full(p,adapter,tasks)
        flat=await ab.run_flat(p,adapter,tasks)
        assert full['archive_size']>1 and full['iterations']==3
        assert len(flat['draw_means'])==4
        print(json.dumps({'full':full,'flat':flat,'paid_requests':0},indent=2))
if __name__=='__main__':asyncio.run(main())
