"""Fetch pinned official CO-Bench files for the six-task engineering smoke."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
REVISION='6e561a36254d4315b8c2d155e81a465b634e87e1'
ROOT=Path(__file__).resolve().parents[3]/'experiments/cobench_preparation'
SELECTED={'Bin packing - one-dimensional':'binpack1.txt','Flow shop scheduling':'tai100_10.txt',
          'Graph colouring':'gcol1.txt','Job shop scheduling':'tai100_20.txt',
          'Open shop scheduling':'tai10_10.txt','Aircraft landing':'airland1.txt'}
def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for task,filename in SELECTED.items():
        for name in ['config.py',filename]:
            relative=task+'/'+name;target=ROOT/'data'/relative
            url=f'https://huggingface.co/datasets/CO-Bench/CO-Bench/resolve/{REVISION}/'+urllib.parse.quote(relative)
            if not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(urllib.request.urlopen(url,timeout=60).read())
            manifest.append({'path':relative,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'url':url})
    tree_path=ROOT/'source_tree.json'
    if not tree_path.exists():
        tree=json.load(urllib.request.urlopen(f'https://huggingface.co/api/datasets/CO-Bench/CO-Bench/tree/{REVISION}?recursive=true&limit=1000'))
        tree_path.write_text(json.dumps({'revision':REVISION,'files':tree},indent=2))
    (ROOT/'download_manifest.json').write_text(json.dumps({'revision':REVISION,'files':manifest},indent=2)+'\n')
    print('Official files ready:',len(manifest))
if __name__=='__main__':main()
