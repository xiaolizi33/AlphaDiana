"""Load explicit IDs from a checksummed MATH-500 snapshot; no remote drift."""
import hashlib
import json
from pathlib import Path
from alphadiana.benchmarks.base import Benchmark, BenchmarkTask
from alphadiana.engine.components import register_benchmark


@register_benchmark('math500')
class Math500Benchmark(Benchmark):
    name = 'math500'

    def load_tasks(self, config):
        data = Path(config['snapshot']).read_bytes()
        if hashlib.sha256(data).hexdigest() != config['sha256']:
            raise ValueError('MATH-500 snapshot checksum mismatch')
        rows = [json.loads(line) for line in data.decode().splitlines()]
        by_id = {r['unique_id']:r for r in rows}
        if len(by_id) != len(rows):
            raise ValueError('Duplicate source IDs')
        ids = config['ids']
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('Provide nonempty unique task IDs')
        tasks = []
        for key in ids:
            row = by_id[key]
            tasks.append(BenchmarkTask(task_id=key, problem=row['problem'], ground_truth=row['answer'],
                                       metadata={'subject':row['subject'], 'level':row['level'],
                                                 'source_id':key}))
        return tasks

    def default_scorer(self):
        return 'math_verify'
