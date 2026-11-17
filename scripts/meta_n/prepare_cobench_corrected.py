"""Download fresh task families before any corrected-campaign model results."""
import hashlib,json,importlib.util
from pathlib import Path
import urllib.parse,urllib.request
REV='6e561a36254d4315b8c2d155e81a465b634e87e1'
ROOT=Path(__file__).resolve().parents[3]/'experiments/cobench_corrected_data'
NAMES=['Assignment problem','Common due date scheduling','Equitable partitioning problem','Generalised assignment problem','Container loading','Corporate structuring','Uncapacitated warehouse location','Resource constrained shortest path','Assortment problem']
def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    tree=json.load(urllib.request.urlopen(f'https://huggingface.co/api/datasets/CO-Bench/CO-Bench/tree/{REV}?recursive=true&limit=1000'))
    (ROOT/'source_tree.json').write_text(json.dumps({'revision':REV,'files':tree},indent=2))
    manifest=[]
    for name in NAMES:
        candidates=sorted([x['path'] for x in tree if x['type']=='file' and x['path'].startswith(name+'/') and not x['path'].endswith('.py')])
        config=ROOT/'data'/name/'config.py'
        if name in NAMES[-3:]:
            spec=importlib.util.spec_from_file_location('co_config',config);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            dev=module.get_dev();candidates=[f for f in candidates if f.split('/')[-1] not in dev]
            assert candidates, 'No held-out file'
            for old in config.parent.iterdir():
                if old.is_file() and old.name!='config.py':
                    archive=ROOT/'excluded_preflight'/name/old.name;archive.parent.mkdir(parents=True,exist_ok=True);old.rename(archive)
        for file in [name+'/config.py',candidates[0]]:
            target=ROOT/'data'/file;target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(urllib.request.urlopen(f'https://huggingface.co/datasets/CO-Bench/CO-Bench/resolve/{REV}/'+urllib.parse.quote(file),timeout=60).read())
            manifest.append({'path':file,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        print(name,candidates[0],flush=True)
    (ROOT/'manifest.json').write_text(json.dumps({'revision':REV,'files':manifest},indent=2))
if __name__=='__main__':main()
