"""Request actual CMake File API interfaces without rebuilding native products."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
run = root.parents[1]
repo = Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh')
binary = repo / 'artifacts/obj/coreclr/browser.wasm64.Release/native-pthreads'
product = repo / 'artifacts/bin/coreclr/browser.wasm64.Release/native-pthreads'
guest = root / 'Guest/DirectPeGuest-1e9f8bd1'
output = guest / 'NativeProfile'
output.mkdir(exist_ok=True)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
tracked = list((product / 'corerun-link').rglob('*')) + [product / 'corerun.js', product / 'corerun.wasm', product / 'IL/System.Private.CoreLib.dll']
tracked = [p for p in tracked if p.is_file()]
snapshot = lambda: {str(p): {'sha256': digest(p), 'bytes': p.stat().st_size} for p in tracked}
before = snapshot()
cache_before = (binary / 'CMakeCache.txt').read_text()
compiler_inputs = (binary / 'cmake_compiler_inputs.txt').read_text()
query = binary / '.cmake/api/v1/query/client-ue-web-support/query.json'
query.parent.mkdir(parents=True, exist_ok=True)
query.write_text(json.dumps({'requests': [{'kind':'codemodel','version':2}, {'kind':'cache','version':2}, {'kind':'toolchains','version':1}]}))
env = os.environ.copy()
sdk = run / 'Toolchain/emsdk'
env.update(EM_CONFIG=str(sdk / '.emscripten'), EMSDK_PYTHON=str(sdk / 'python/3.13.3_64bit/python.exe'),
           EM_LLVM_ROOT=str(run / 'Toolchain/fixed-llvm/bin'),
           EM_CACHE=str(root / 'EmscriptenCache/6.0.10-fixed-6c5ce14d-js-eh-pthreads'),
           EM_FROZEN_CACHE='1', EMCC_CORES='2', CMAKE_BUILD_PARALLEL_LEVEL='2')
command = ['C:/Program Files/CMake/bin/cmake.exe', '-S', str(repo / 'src/coreclr'), '-B', str(binary)]
with (output / 'file-api-configure.log').open('w') as log:
    result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
after = snapshot()
cache_after = (binary / 'CMakeCache.txt').read_text()
manifest = {'scope': 'Standard CMake File API query and unchanged-cache configure only. No compile/link or RSP execution.',
            'command': command, 'exit_code': result.returncode, 'native_product_before': before,
            'native_product_after': after, 'native_product_unchanged': before == after,
            'cache_bytes_unchanged': cache_before == cache_after,
            'compiler_inputs_unchanged': compiler_inputs == (binary / 'cmake_compiler_inputs.txt').read_text()}
if result.returncode == 0:
    reply = binary / '.cmake/api/v1/reply'
    index = max(reply.glob('index-*.json'), key=lambda p:p.stat().st_mtime_ns)
    index_data = json.loads(index.read_text())
    codemodel_object = next(item for item in index_data['objects'] if item['kind'] == 'codemodel')
    codemodel = json.loads((reply / codemodel_object['jsonFile']).read_text())
    target_object = next(item for item in codemodel['configurations'][0]['targets'] if item['name'] == 'corerun')
    target = json.loads((reply / target_object['jsonFile']).read_text())
    for path in [index, reply / codemodel_object['jsonFile'], reply / target_object['jsonFile']]:
        (output / path.name).write_bytes(path.read_bytes())
    manifest.update(index=str(index), codemodel=str(reply / codemodel_object['jsonFile']), corerun_target=str(reply / target_object['jsonFile']),
                    corerun_target_sha256=digest(reply / target_object['jsonFile']))
manifest['passed'] = result.returncode == 0 and before == after and manifest['compiler_inputs_unchanged'] and manifest['cache_bytes_unchanged']
(output / 'file-api-query-results.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({k:v for k,v in manifest.items() if k not in ['native_product_before','native_product_after']}, indent=2))
raise SystemExit(0 if manifest['passed'] else 1)
