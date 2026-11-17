"""One execution-limit object shared by prompts and CO-Bench scoring."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceContract:
    instance_timeout_seconds: int = 10
    evaluation_timeout_seconds: int = 300
    helper_budget_seconds: float = 5.0

    def __post_init__(self):
        if not 0 < self.helper_budget_seconds < self.instance_timeout_seconds:
            raise ValueError('Helper budget must leave time for setup and fallback')
        if self.evaluation_timeout_seconds < self.instance_timeout_seconds:
            raise ValueError('Task timeout must cover at least one instance')

    def prompt(self):
        return (f'EXECUTION RESOURCE CONTRACT: The evaluator hard-kills each solve(**kwargs) '
                f'after {self.instance_timeout_seconds} seconds wall time, including helper execution. '
                f'All helpers combined must use at most {self.helper_budget_seconds:g} seconds '
                'per instance; check elapsed time inside inner loops and return a feasible fallback '
                'before the hard limit. No network, file access, subprocesses or inner LLM calls. '
                'Python standard library only; input objects may be numpy arrays, accessible by '
                'indexing, len() and tolist(). Implement the supplied solve(**kwargs) returning '
                'the specified dictionary; do not implement a no-argument numeric solver.')

    def scorer_config(self):
        return {'instance_timeout': self.instance_timeout_seconds,
                'evaluation_timeout': self.evaluation_timeout_seconds}
