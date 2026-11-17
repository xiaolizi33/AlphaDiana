"""Verify staged source in a fresh checkout and fresh virtualenv without model calls."""
import io,json,os,subprocess,tarfile,tempfile
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
UPSTREAM='b7081843d3c7b0e0f418ca10aaf2ccbff856e7f8'
def run(args,cwd=None):subprocess.run([str(x) for x in args],cwd=cwd,check=True)
def main():
    with tempfile.TemporaryDirectory(prefix='meta_n_clean_') as directory:
        root=Path(directory);repo=root/'AlphaDiana';repo.mkdir()
        data=subprocess.check_output(['git','-C',str(REPO),'archive','HEAD'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:archive.extractall(repo,filter='data')
        patch=subprocess.check_output(['git','-C',str(REPO),'diff','--cached','--binary'])
        if patch:subprocess.run(['git','apply','--binary'],input=patch,cwd=repo,check=True)
        run(['git','clone','--quiet','--shared',REPO.parent/'meta-n',root/'meta-n'])
        run(['git','checkout','--quiet','--detach',UPSTREAM],root/'meta-n')
        run(['uv','venv','--python','3.11',root/'.venv'])
        python=root/'.venv/bin/python'
        run(['uv','pip','install','--python',python,'-r',repo/'configs/meta_n/requirements-reproduction.lock'])
        run(['uv','pip','install','--python',python,'--no-deps','-e',root/'meta-n','-e',repo])
        run([python,'-m','pytest',repo/'tests/harness/meta_n',repo/'tests/harness/test_native_registry_integration.py','-q'],root)
        run([python,'-m','alphadiana.cli','--help'],root)
        record={'status':'passed','fresh_environment':True,'no_existing_experiment_artifacts':True,
                'paid_model_calls':0,'upstream_commit':UPSTREAM}
        output=REPO.parent/'experiments/debug_runs/20261117_submission_review/clean_checkout.json'
        output.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':main()
