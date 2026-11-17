import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parent
GUEST=ROOT/'Guest/DirectPeGuest-1e9f8bd1'
KIT=Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh/artifacts/bin/coreclr/browser.wasm64.Release/native-pthreads/corerun-link')
libraries=[]
for name in ('libSystem.Native.Browser.js','libSystem.Native.Browser.Utils.js'):
    path=KIT/name
    stamps=set(re.findall(r'[0-9a-f]{40}',path.read_text()))
    if len(stamps)!=1:raise RuntimeError('Ambiguous actual emitted JS stamp: '+str(path))
    libraries.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'emitted_git_hash':stamps.pop()})
if libraries[0]['emitted_git_hash']!=libraries[1]['emitted_git_hash']:raise RuntimeError('Actual two JS stamps differ')
path=GUEST/'Source/bootstrap.js';before=path.read_text()
pattern=r'runtimeBuildInfo:\s*\{\s*gitHash:\s*(?:null|"[0-9a-f]{40}")\s*\}'
if len(re.findall(pattern,before))!=1:raise RuntimeError('Expected one reviewed bootstrap source stamp anchor')
after=re.sub(pattern,'runtimeBuildInfo: { gitHash: "'+libraries[0]['emitted_git_hash']+'" }',before)
path.write_text(after)
report={'native_source_revision':'1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791','scope':'Source bootstrap bound to actual emitted production JS identities, not a guessed C++ source stamp',
        'libraries':libraries,'bootstrap_path':str(path),'bootstrap_before_sha256':hashlib.sha256(before.encode()).hexdigest(),
        'bootstrap_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'two_slot_runtime_internals_only':True}
(GUEST/'bootstrap-provenance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(libraries[0]['emitted_git_hash'])
