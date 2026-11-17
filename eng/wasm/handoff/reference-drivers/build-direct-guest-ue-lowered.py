"""Normal independent CMake target build; never execute a native product response file."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
run = root.parents[1]
guest = root / 'Guest/DirectPeGuest-1e9f8bd1'
sdk = run / 'Toolchain/emsdk'
output = guest / 'UeLowered'
output.mkdir(exist_ok=True)
env = os.environ.copy()
env.update(EM_CONFIG=str(sdk / '.emscripten'), EMSDK_PYTHON=str(sdk / 'python/3.13.3_64bit/python.exe'),
           EM_LLVM_ROOT=str(run / 'Toolchain/fixed-llvm/bin'),
           EM_CACHE=str(root / 'EmscriptenCache/6.0.10-fixed-6c5ce14d-js-eh-pthreads'),
           EM_FROZEN_CACHE='1', EMCC_CORES='2', CMAKE_BUILD_PARALLEL_LEVEL='2')
cmake = 'C:/Program Files/CMake/bin/cmake.exe'
ninja = 'C:/Program Files/Microsoft Visual Studio/18/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
initial_abi = '-m64 -pthread -fexceptions'
configure = [cmake, '-S', str(guest / 'Source'), '-B', str(output), '-G', 'Ninja',
             '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_MAKE_PROGRAM=' + ninja,
             '-DCMAKE_TOOLCHAIN_FILE=' + str(sdk / 'upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'),
             '-DCMAKE_C_FLAGS=' + initial_abi, '-DCMAKE_CXX_FLAGS=' + initial_abi,
             '-DCMAKE_EXE_LINKER_FLAGS=-m64',
             '-DDIRECT_PE_NATIVE_PROFILE=' + str(guest / 'NativeProfile/ue-lowered-profile.cmake'),
             '-DDIRECT_PE_GUEST_INPUTS=' + str(guest / 'Preparation/guest-inputs.cmake')]
build = [cmake, '--build', str(output), '--target', 'direct_pe_guest', '--parallel', '2']
provenance = json.loads((guest / 'NativeProfile/native64-profile-provenance.json').read_text())
inputs = [Path(row['installed_kit']) for row in provenance['archive_sources']]
inputs += [Path(p) for p in provenance['headers']] + [Path(p) for p in provenance['production_js']]
metadata = json.loads((guest / 'Preparation/metadata.json').read_text())
inputs += [Path(row['path']) for row in metadata['explicitInputs']]
snapshot = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
before = snapshot()
receipt = {'source_revision':'1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791', 'scope':'Actual normal DirectPeGuest CMake build; no guest run claimed by this build receipt.',
           'start_utc':datetime.now(timezone.utc).isoformat(), 'configure_command':configure, 'build_command':build,
           'environment':{name:env[name] for name in ['EM_CONFIG','EMSDK_PYTHON','EM_LLVM_ROOT','EM_CACHE','EM_FROZEN_CACHE','EMCC_CORES','CMAKE_BUILD_PARALLEL_LEVEL']},
           'inputs_before':before}
with (output / 'configure.log').open('w') as log:
    child = subprocess.Popen(configure, env=env, stdout=log, stderr=subprocess.STDOUT)
    receipt['configure_pid'] = child.pid
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    receipt['configure_exit'] = child.wait()
if receipt['configure_exit'] == 0:
    with (output / 'build.log').open('w') as log:
        child = subprocess.Popen(build, env=env, stdout=log, stderr=subprocess.STDOUT)
        receipt['build_pid'] = child.pid
        (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        receipt['build_exit'] = child.wait()
receipt.update(end_utc=datetime.now(timezone.utc).isoformat(), inputs_after=snapshot())
receipt['inputs_unchanged'] = receipt['inputs_before'] == receipt['inputs_after']
receipt['passed'] = receipt['configure_exit'] == 0 and receipt.get('build_exit') == 0 and receipt['inputs_unchanged']
(output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs_before','inputs_after','environment','configure_command','build_command']}, indent=2))
raise SystemExit(0 if receipt['passed'] else 1)
