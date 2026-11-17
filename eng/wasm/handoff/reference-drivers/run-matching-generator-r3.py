"""Own the normal build process and preserve its real exit/PID/source identity."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
run = root.parents[1]
repo = Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh')
logs = root / 'Logs'
logs.mkdir(parents=True, exist_ok=True)
sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
status = subprocess.check_output(['git', '-C', str(repo), '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', 'status', '--porcelain'], text=True)
if status or sha != '1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791':
    raise RuntimeError('The reviewed source identity is not clean/expected; do not start a heavy build')
for prior_name in ['full-native-profile-r3-result.json', 'matching-framework-r3-result.json']:
    prior = json.loads((root / prior_name).read_text())
    if prior.get('exit_code') != 0 or prior.get('source_commit') != sha:
        raise RuntimeError('Matching successful native and framework graphs required before tools')

env = os.environ.copy()
env.update(DOTNET_INSTALL_DIR='C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/wasm64-eden-main/.dotnet',
           DOTNET_ROOT='C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/wasm64-eden-main/.dotnet',
           EMSDK_PATH=str(run / 'Toolchain/emsdk'), EM_CONFIG=str(run / 'Toolchain/emsdk/.emscripten'),
           EMSDK_PYTHON=str(run / 'Toolchain/emsdk/python/3.13.3_64bit/python.exe'),
           EM_LLVM_ROOT=str(run / 'Toolchain/fixed-llvm/bin'),
           EM_CACHE=str(root / 'EmscriptenCache/6.0.10-fixed-6c5ce14d-js-eh-pthreads'),
           EMCC_CORES='2', CMAKE_BUILD_PARALLEL_LEVEL='2')
clang_hash = hashlib.sha256((Path(env['EM_LLVM_ROOT']) / 'clang.exe').read_bytes()).hexdigest()
if clang_hash != '6c5ce14d830a38be10991a4d639a881b32d6399e3d59717cf8f9d3ce732590a4':
    raise RuntimeError('The verified fixed normal Clang changed')
command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root / 'run-matching-generator-r3.ps1')]
start = datetime.now(timezone.utc).isoformat()
with (logs / 'matching-generator-r3-driver.log').open('w') as output:
    child = subprocess.Popen(command, cwd=repo, env=env, stdout=output, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    receipt = {'source_commit': sha, 'source_clean': True, 'pid': child.pid, 'start_utc': start,
               'command': command, 'driver_sha256': hashlib.sha256((root / 'run-matching-generator-r3.ps1').read_bytes()).hexdigest(),
               'normal_entry': str(repo / 'eng/common/build.ps1'),
               'environment': {k: env[k] for k in ('DOTNET_INSTALL_DIR', 'DOTNET_ROOT', 'EMSDK_PATH', 'EM_CONFIG', 'EMSDK_PYTHON', 'EM_LLVM_ROOT', 'EM_CACHE', 'EMCC_CORES', 'CMAKE_BUILD_PARALLEL_LEVEL')},
               'clang_sha256': clang_hash, 'managed_project': 'src/coreclr/tools/aot/ILCompiler.ReadyToRun/ILCompiler.ReadyToRun.csproj',
               'write_set': [str(repo / 'artifacts'), str(root / 'ICU/work'), env['EM_CACHE'], str(logs)],
               'note': 'Normal tools may also populate their existing NuGet/SDK caches. No old runtime/UE native product is in the compilation write set.'}
    (root / 'matching-generator-r3-invocation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'pid': child.pid, 'source_commit': sha, 'log': str(logs / 'matching-generator-r3-driver.log')}, indent=2), flush=True)
    exit_code = child.wait()
receipt.update(end_utc=datetime.now(timezone.utc).isoformat(), exit_code=exit_code)
(root / 'matching-generator-r3-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('matching_generator_exit=' + str(exit_code), flush=True)
raise SystemExit(exit_code)
