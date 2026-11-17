"""Fresh normal managed source builds after all matching producer graphs exit0."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import os
import subprocess
ROOT=Path(__file__).resolve().parent
GUEST=ROOT/'Guest/DirectPeGuest-1e9f8bd1'
SHA='1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791'
DOTNET=Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/wasm64-eden-main/.dotnet/dotnet.exe')
for name in ('full-native-profile-r3','matching-framework-r3','matching-generator-r3'):
    row=json.loads((ROOT/(name+'-result.json')).read_text())
    if row['exit_code']!=0 or row['source_commit']!=SHA:raise RuntimeError('No matching completed producer '+name)
env=os.environ.copy();env.update(DOTNET_ROOT=str(DOTNET.parent),DOTNET_INSTALL_DIR=str(DOTNET.parent))
def one(label,relative):
    path=GUEST/'Source'/relative
    argv=[str(DOTNET),'build',str(path),'-c','Release']
    completed=subprocess.run(argv,cwd=GUEST,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log=GUEST/(label+'-build.log');log.write_text(completed.stdout,encoding='utf-8')
    return {'label':label,'argv':argv,'exit_code':completed.returncode,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
    results=list(workers.map(lambda pair:one(*pair),[('probe','Probe/DirectPeGuestProbe.csproj'),('helper-host','HelperHost/PortableHelperHost.csproj')]))
report={'runtime_source_revision':SHA,'scope':'Fresh source builds only; no CLR/Wasm guest execution','results':results,'passed':all(row['exit_code']==0 for row in results)}
(GUEST/'managed-build-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
