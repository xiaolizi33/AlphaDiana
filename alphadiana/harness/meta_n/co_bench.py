"""CO-Bench programs scored by upstream evaluator in a key-free macOS sandbox."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from alphadiana.engine.components import register_agent, register_scorer
from alphadiana.scorer.base import Scorer, ScoreResult
from .agent import MetaNAgent


@register_agent('meta_n_co_bench')
class COBenchAgent(MetaNAgent):
    async def _solve(self, task):
        response = await super()._solve(task)
        response.metadata['executor'] = 'deferred_to_co_bench_official_scorer'
        return response

    def execute_script(self, script):
        # Execution is deferred to the scorer, which owns the held-out instances.
        return {'answer': script, 'stdout': '', 'stderr': '', 'exit_code': 0, 'timed_out': False}


def evaluate_program(script, task_name, config):
    data = Path(config['data_dir']).resolve()
    # A file may contain 100 instances: the parent deadline must accommodate
    # every allowed per-instance execution, including non-dev normalization.
    import importlib.util
    spec = importlib.util.spec_from_file_location('_co_count', data/task_name/'config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = [p for p in (data/task_name).iterdir() if p.is_file() and p.suffix != '.py']
    dev = module.get_dev() if hasattr(module, 'get_dev') else None
    if config['eval_split'] == 'dev' and dev:
        files = [p for p in files if p.name in dev]
    instances = sum(len(module.load_data(str(p))) for p in files)
    if not instances:
        raise RuntimeError('No instances available to evaluator')
    parent_timeout = max(config.get('evaluation_timeout',180),
                         instances * (config.get('instance_timeout',3) + 2) + 60)
    import meta_n
    allowed = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
               Path(meta_n.__file__).resolve().parent, data]
    with tempfile.TemporaryDirectory(prefix='co_eval_') as directory:
        root = Path(directory).resolve()
        (root/'program.py').write_text(script)
        worker = '''import json, pathlib
from meta_n.integrations.co_bench import _TaskEvaluator
if __name__ == '__main__':
    ev = _TaskEvaluator(%r, pathlib.Path(%r), timeout=%r, instance_workers=1)
    method = ev.evaluate_test if %r == 'test' else ev.evaluate
    result = method(pathlib.Path('program.py').read_text())
    pathlib.Path('result.json').write_text(json.dumps(result, default=str))
''' % (task_name, str(data), config.get('instance_timeout', 3), config['eval_split'])
        (root/'worker.py').write_text(worker)
        exceptions = ' '.join('(require-not (subpath "%s"))' % p for p in allowed)
        profile = '''(version 1)(allow default)(deny network*)
(deny file-read-data (require-all (subpath "/Users") %s) (subpath "/Volumes")
(require-all (subpath "/private/var/folders") (require-not (subpath "%s")) %s))
(deny file-write* (require-all (require-not (subpath "%s")) (require-not (literal "/dev/null"))))
''' % (exceptions, root, exceptions, root)
        with (root/'out').open('w+') as out, (root/'err').open('w+') as err:
            proc = subprocess.Popen(['/usr/bin/sandbox-exec','-p',profile,sys.executable,'-I',str(root/'worker.py')],
                cwd=root, env={'PATH':'/usr/bin:/bin','TMPDIR':str(root),'OPENBLAS_NUM_THREADS':'1'},
                stdout=out, stderr=err, start_new_session=True)
            try:
                proc.wait(timeout=parent_timeout)
            except subprocess.TimeoutExpired:
                raise RuntimeError('CO evaluator batch deadline exceeded; audit infrastructure before resuming')
            finally:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                except PermissionError:
                    if proc.poll() is None:
                        proc.kill()
                proc.wait()
            if proc.returncode or not (root/'result.json').exists():
                err.seek(0)
                raise RuntimeError('CO evaluator infrastructure failed: '+err.read()[-3000:])
        result=json.loads((root/'result.json').read_text())
        if 'raw_results' in result and not result['raw_results']:
            raise RuntimeError('No instances in selected official split; refuse empty evaluation')
        prefix=config['eval_split']
        if not math.isfinite(result[prefix+'_score']):
            raise RuntimeError('CO evaluator returned a non-finite score')
        return {'score':result[prefix+'_score'], 'feedback':result[prefix+'_feedback'], 'official_result':result}


@register_scorer('co_bench_official')
class COBenchScorer(Scorer):
    name = 'co_bench_official'
    def setup(self, config):
        self.config = config
    def score(self, task, response):
        if response.finish_reason != 'stop':
            return ScoreResult(False,0.,None,'',rationale='Incomplete output; not executed')
        name=self.config['task_names'][task.task_id]
        result=evaluate_program(response.answer,name,self.config)
        # CO-Bench has continuous quality scores; correct means positive score only.
        return ScoreResult(result['score']>0,result['score'],None,response.answer,
                           rationale=result['feedback'],metadata=result)
