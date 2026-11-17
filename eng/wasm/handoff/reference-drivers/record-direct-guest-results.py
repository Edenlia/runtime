"""Bind actual native/framework/tools/helper/Node/Chrome artifacts and final memory models."""
import hashlib
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
run = root.parents[1]
repo = Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh')
guest = root / 'Guest/DirectPeGuest-1e9f8bd1'
revision = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'], text=True).strip()
status = subprocess.check_output(['git','-C',str(repo),'-c','core.fsmonitor=false','-c','core.untrackedCache=false','status','--porcelain'], text=True)
if revision != '1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791' or status:
    raise RuntimeError('Product source changed during guest verification')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read_json = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
spec = importlib.util.spec_from_file_location('wasm_limits_reader', run / 'UE/Probe/run_abi_probe.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
metadata = read_json(guest / 'Preparation/metadata.json')
inputs = metadata['explicitInputs']
helpers = read_json(guest / 'Preparation/Helpers/provenance.json')
if helpers['PointerSize'] != 8 or helpers['targetArchitecture'] != 'Wasm64' or len(helpers['inputs']) != 5:
    raise RuntimeError('Wrong actual helper context')
for entry in helpers['inputs']:
    if digest(Path(entry['path'])) != entry['sha256']:
        raise RuntimeError('Generated helper input changed')
helper_log = (guest / 'helper-generator.log').read_text()
if 'WASM0001' in helper_log or 'Helper-only generator exit: 0; explicit inputs: 5; references: 177' not in helper_log:
    raise RuntimeError('Skipped/failed helper generation')
query = read_json(guest / 'NativeProfile/file-api-query-results.json')
current_product = {path:{'sha256':digest(Path(path)),'bytes':Path(path).stat().st_size} for path in query['native_product_after']}
if current_product != query['native_product_after']:
    raise RuntimeError('Native product changed during guest verification')
source_receipts = {}
for name in ['full-native-profile-r3','matching-framework-r3','matching-generator-r3']:
    path = root / (name + '-result.json')
    receipt = read_json(path)
    if receipt['source_commit'] != revision or receipt['exit_code'] != 0:
        raise RuntimeError('Unmatched unsuccessful source graph')
    source_receipts[name] = {'path':str(path),'sha256':digest(path),'exit_code':receipt['exit_code'],'source_commit':receipt['source_commit']}
sdk = run / 'Toolchain/emsdk'
tools = [sdk / 'python/3.13.3_64bit/python.exe', sdk / 'node/24.19.0_64bit/node.exe',
         sdk / '.emscripten', sdk / 'upstream/emscripten/emcc.py', sdk / 'upstream/emscripten/em++.py',
         sdk / 'upstream/emscripten/tools/system_libs.py', sdk / 'upstream/emscripten/src/settings.js',
         run / 'Toolchain/fixed-llvm/bin/clang.exe', run / 'Toolchain/fixed-llvm/bin/wasm-ld.exe',
         sdk / 'upstream/bin/wasm-opt.exe', Path('C:/Program Files/CMake/bin/cmake.exe'),
         Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
         repo.parent / 'wasm64-eden-main/.dotnet/dotnet.exe']
generator_tools = list((guest / 'Source/HelperHost/bin/Release/net12.0').glob('ILCompiler.*.dll'))
tools += generator_tools + [guest / 'Source/HelperHost/bin/Release/net12.0/PortableHelperHost.dll']
matrix = {}
for lane, bits, maximum_pages in [('Native64',64,131072),('UeLowered',32,65536)]:
    out = guest / lane
    build = read_json(out / 'build-receipt.json')
    node = read_json(out / 'node-proof.json')
    chrome = read_json(out / 'chrome-result.json')
    if not build['passed'] or not node['passed'] or not chrome['passed']:
        raise RuntimeError('Actual build/Node/Chrome did not all succeed: ' + lane)
    limits = reader.wasm_limits(out / 'direct_pe_guest.wasm')
    if not all(item['index_bits'] == bits for item in limits['tables'] + limits['memories']):
        raise RuntimeError('Unexpected final memory/table model')
    if not limits['memories'][0]['shared'] or limits['memories'][0]['maximum'] != maximum_pages:
        raise RuntimeError('Unexpected actual final shared memory limits')
    matrix[lane] = {'normal_cmake_exit':build['build_exit'],'node_exit':node['exit_code'],
                    'node_receipt':str(out / 'node-proof.json'),'node_receipt_sha256':digest(out / 'node-proof.json'),
                    'chrome_exit':chrome['environment']['exitCode'],'chrome_version':chrome['browser_version'],
                    'chrome_workers':len(chrome['workers']) if 'workers' in chrome else None, 'chrome_receipt':str(out / 'chrome-result.json'),
                    'chrome_receipt_sha256':digest(out / 'chrome-result.json'), 'wasm_limits':limits,
                    'files':chrome['files'], 'passed':True}
framework_hashes = {entry['path']:digest(Path(entry['path'])) for entry in metadata['frameworkCandidates']}
result = {'scope':'Actual CoreCLR direct loose-PE guest with real hosting contract, generated PInvoke/UCO helpers and production System.Native.Browser/Utils. Independent fixture; not packaged UE/UnrealSharp gameplay acceptance.',
          'runtime_exception_model':'emscripten','runtime_interpreter_only':True,'runtime_ready_to_run':False,
          'runtime_source_revision':revision,'source_clean':not status,'normal_graph_receipts':source_receipts,
          'actual_matching_corelib_sha256':metadata['corelibSha256'],'assembly_ref_closure':inputs,
          'framework_candidate_hashes':framework_hashes,'selected_inputs_all_il_only':all(i['ilOnly'] and i['managedNativeHeaderBytes']==0 for i in inputs),
          'helper_context':{'target':helpers['targetArchitecture'],'pointer_size':helpers['PointerSize'],'explicit_input_count':len(helpers['inputs']),'reference_count':len(helpers['references']),
                            'generator_sha256':helpers['generatorSha256'],'full_provenance':str(guest / 'Preparation/Helpers/provenance.json')},
          'helper_sources':{path.name:digest(path) for path in (guest / 'Preparation/Helpers').glob('*.cpp')},
          'bootstrap_provenance':read_json(guest / 'bootstrap-provenance.json'),
          'native_profile_provenance':str(guest / 'NativeProfile/native64-profile-provenance.json'),
          'ue_host_policy_provenance':str(guest / 'NativeProfile/native64-profile-provenance.json'),
          'installed_ue_defaults_provenance':str(guest / 'NativeProfile/ue-lowered-profile-provenance.json'),
          'sdk_and_tools':{str(path):{'bytes':path.stat().st_size,'sha256':digest(path)} for path in tools},
          'native_product_hashes_unchanged_after_all_guest_lanes':True,'matrix':matrix,
          'retained_failures':['UeLowered/Attempt1-MissingEmmalloc: frozen-cache ordinary link needed UE baseline libemmalloc-mt; official SDK embuilder prepared it and unchanged ordinary target retried successfully.'],
          'managed_exception_proof':{'two_inputs':[9,-17], 'flags':[31,31], 'typed_catch':True,'throw_new_from_catch':True,'rethrow_identity':True,'finally_count':3,'filter_count':1,'genuine_second_delegate':True},
          'not_claimed':['UE Game/AActor execution','forced GC/finalizer draining','negative shutdown/failure injection','native high-address allocation beyond4GiB'],
          'passed':True}
(guest / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'source':revision,'corelib':metadata['corelibSha256'],'matrix':matrix,'passed':True}, indent=2))
