"""Run from any directory; key stays in environment, never in Diana config."""
import json
import os
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[2]
    os.chdir(repo)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        os.environ["DEEPSEEK_API_KEY"] = (repo.parent / "apikey").read_text().strip().strip("\"'")
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    from alphadiana.engine.runner import Runner
    from dataclasses import asdict
    config = ExperimentConfig.from_yaml(str(repo / "configs/meta_n/zero_pilot.yaml"))
    errors = ConfigValidator().validate(config)
    if errors:
        raise ValueError(errors)
    runner = Runner(config)
    try:
        runner.setup()
        summary = runner.run()
        output = Path(config.output_dir) / "pilot_summary.json"
        output.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str) + "\n")
        print(output)
    finally:
        runner.teardown()


if __name__ == "__main__":
    main()
