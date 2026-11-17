from pathlib import Path
import hashlib
import json
import os
import subprocess
ROOT=Path(__file__).resolve().parent
GUEST=ROOT/'Guest/DirectPeGuest-1e9f8bd1'
DOTNET=Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/wasm64-eden-main/.dotnet/dotnet.exe')
manifest=GUEST/'Preparation/helper-inputs.json'
output=GUEST/'Preparation/Helpers'
if output.exists():raise RuntimeError('Use a fresh helper output; preserve prior generation')
host=GUEST/'Source/HelperHost/bin/Release/net12.0/PortableHelperHost.dll'
argv=[str(DOTNET),str(host),str(manifest),str(output)]
env=os.environ.copy();env.update(DOTNET_ROOT=str(DOTNET.parent),DOTNET_INSTALL_DIR=str(DOTNET.parent))
result=subprocess.run(argv,env=env,cwd=GUEST,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
log=GUEST/'helper-generator.log';log.write_text(result.stdout,encoding='utf-8')
report={'runtime_source_revision':'1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791','argv':argv,'exit_code':result.returncode,
        'host_sha256':hashlib.sha256(host.read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()} if output.exists() else {}}
(GUEST/'helper-generation-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(result.returncode)
