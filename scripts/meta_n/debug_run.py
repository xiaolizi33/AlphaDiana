"""Persist each debugging invocation, complete stdout/stderr and return code."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import hashlib
import shutil

def main():
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--group',default='20261116_resource_contract_fix');p.add_argument('command',nargs=argparse.REMAINDER);args=p.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if Path(args.group).name != args.group or Path(args.label).name != args.label:
        p.error('Group and label must be single directory names')
    root=Path(__file__).resolve().parents[3]/'experiments/debug_runs'/args.group
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');run=root/(stamp+'_'+args.label);run.mkdir(parents=True)
    start=time.monotonic();record={'command':command,'cwd':str(Path.cwd()),'started_utc':stamp,'status':'running'}
    (run/'record.json').write_text(json.dumps(record,indent=2))
    repo=Path(__file__).resolve().parents[2]
    sources=[*sorted((repo/'alphadiana/harness/meta_n').glob('*.py')),
             *sorted((repo/'scripts/meta_n').glob('*.py'))]
    record['source_hashes']={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for source in sources:
        target=run/'sources'/source.relative_to(repo)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (run/'record.json').write_text(json.dumps(record,indent=2))
    with (run/'stdout.log').open('w') as out,(run/'stderr.log').open('w') as err:
        try:
            result=subprocess.run(command,stdout=out,stderr=err)
            returncode=result.returncode
        except BaseException as exc:
            err.write(f'{type(exc).__name__}: {exc}\n')
            returncode=130 if isinstance(exc, KeyboardInterrupt) else 127
    record.update(status='passed' if returncode==0 else 'failed',returncode=returncode,elapsed_seconds=time.monotonic()-start)
    (run/'record.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Debug record:',run,'exit:',returncode,flush=True)
    for name in ['stdout.log','stderr.log']:
        data=(run/name).read_text();print(name+':\n'+data[-5000:])
    raise SystemExit(returncode)
if __name__=='__main__':main()
