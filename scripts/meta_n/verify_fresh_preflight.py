"""Verify documented first-run initialization into empty artifact directories."""
import asyncio,sys,tempfile
from pathlib import Path
import cobench_corrected
import recursive_ablation
import recursive_ablation_16k

def main():
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder);old=sys.argv
        try:
            cobench_corrected.ROOT=base/'corrected';sys.argv=['cobench_corrected.py','--stage','validate'];cobench_corrected.main()
            for module,name in [(recursive_ablation,'ablation8k'),(recursive_ablation_16k,'ablation16k')]:
                module.ROOT=base/name;asyncio.run(module.main_async('validate'))
            assert len(list(base.glob('*/protocol.json')))==3
            assert len(list(base.glob('*/implementation.json')))==3
            print('Three empty-directory preflights passed; no model requests.')
        finally:sys.argv=old
if __name__=='__main__':main()
