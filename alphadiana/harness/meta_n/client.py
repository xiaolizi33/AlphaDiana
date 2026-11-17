"""Small OpenAI-compatible adapter for the upstream solver, with usage and budget ledger."""
import fcntl
import json
import os
import uuid
from pathlib import Path
from openai import AsyncOpenAI


class SolverClient:
    def __init__(self, config):
        self.config = config
        self.client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                                 base_url=config["api_base"], max_retries=0,
                                 timeout=config.get('request_timeout_seconds', 60))
        self.ledger = Path(config["budget_ledger"]).expanduser().resolve()
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.spent = 0.0

    async def complete(self, messages, temperature=0, seed=None):
        self.request_id = uuid.uuid4().hex
        journal = self.config.get('request_log_dir')
        path = Path(journal) / (self.request_id + '.json') if journal else None
        record = {'request_id': self.request_id, 'messages': messages,
                  'temperature': temperature, 'seed_requested': seed, 'seed_sent': False,
                  'model': self.config.get('model'), 'max_tokens': self.config.get('max_tokens'),
                  'status': 'attempt_started'}
        self.response, self.usage = None, {}
        self.messages, self.reserve, self.request_sent = messages, 0., False
        def persist():
            if path:
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
                temporary.replace(path)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            persist()
        halt = self.config.get("halt_file")
        try:
            if halt and Path(halt).exists():
                raise RuntimeError("Campaign halted after prior request error; audit required")
            result = await self._complete(messages, temperature=temperature, seed=seed)
            record.update(status='complete', response=self.response, usage=self.usage,
                          reserved_cny=self.reserve)
            return result
        except BaseException as exc:
            record.update(status='failed', error_type=type(exc).__name__, error=str(exc),
                          response=self.response, usage=self.usage, reserved_cny=self.reserve)
            if halt and not Path(halt).exists():
                Path(halt).parent.mkdir(parents=True, exist_ok=True)
                Path(halt).write_text(json.dumps({"error_type": type(exc).__name__,
                                                 "message": str(exc)}, ensure_ascii=False) + "\n")
            raise
        finally:
            record['request_sent'] = self.request_sent
            persist()

    async def _complete(self, messages, temperature=0, seed=None):
        cfg = self.config
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
        if input_bound > cfg.get("input_token_bound", 16000):
            raise ValueError("Input exceeds configured conservative token bound")
        # Conservative CNY reserves, NOT provider billing: >= published peak
        # Flash rates at 10 CNY/USD on 2026-11-14. Cache discounts ignored.
        reserve = (input_bound * 3 + cfg["max_tokens"] * 12) / 1e6
        with self.ledger.open("a+") as ledger:
            fcntl.flock(ledger, fcntl.LOCK_EX)
            ledger.seek(0)
            entries = [json.loads(line) for line in ledger if line.strip()]
            total = sum(row["reserved_cny"] for row in entries) + cfg.get("prior_cost_cny", 0.000042)
            scope = cfg.get("budget_scope", "zero_pilot")
            pilot_total = sum(row["reserved_cny"] for row in entries if row.get("scope", "zero_pilot") == scope)
            if total + reserve > cfg.get("global_cap_cny", 50) or pilot_total + reserve > cfg.get("pilot_cap_cny", 1):
                raise RuntimeError("Budget reservation refused; no request sent")
            branches = cfg.get("budget_branches", [])
            token_bound = input_bound + cfg["max_tokens"]
            for branch in branches:
                charged = [row for row in entries if branch in row.get("branches", [])]
                if sum(row["reserved_cny"] for row in charged) + reserve > cfg.get("branch_cny_cap", 5):
                    raise RuntimeError("Branch CNY budget exceeded")
                if sum(row.get("token_bound", 0) for row in charged) + token_bound > cfg.get("branch_token_cap", 300000):
                    raise RuntimeError("Branch token budget exceeded")
            ledger.write(json.dumps({"reserved_cny": reserve, "model": cfg["model"], "scope": scope,
                                     "request_id": self.request_id,
                                     "branches": branches, "token_bound": token_bound}) + "\n")
            ledger.flush()
            os.fsync(ledger.fileno())
        self.spent += reserve
        self.messages = messages
        self.reserve = reserve
        self.request_sent = True
        response = await self.client.chat.completions.create(
            model=cfg["model"], messages=messages, temperature=temperature,
            max_tokens=cfg["max_tokens"], stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
        self.response = response.model_dump()
        self.usage = response.usage.model_dump() if response.usage else {}
        if not self.usage:
            raise RuntimeError("Provider omitted usage; stop pilot")
        self.reserve = reserve
        return response.choices[0].message.content or "", self.usage["total_tokens"]

    async def close(self):
        await self.client.close()
