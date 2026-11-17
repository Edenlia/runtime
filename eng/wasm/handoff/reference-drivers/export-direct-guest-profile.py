"""Author a normal CMake guest profile from actual CMake File API interfaces."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
run = root.parents[1]
repo = Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh')
binary = repo / 'artifacts/obj/coreclr/browser.wasm64.Release/native-pthreads'
product = repo / 'artifacts/bin/coreclr/browser.wasm64.Release/native-pthreads'
kit = product / 'corerun-link'
guest = root / 'Guest/DirectPeGuest-1e9f8bd1'
output = guest / 'NativeProfile'
query = json.loads((output / 'file-api-query-results.json').read_text())
if not query['passed']:
    raise RuntimeError('Unchanged successful native File API query required')
target = json.loads(Path(query['corerun_target']).read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
libraries = []
library_files = []
archive_provenance = []
excluded = []
for fragment in target['link']['commandFragments']:
    if fragment['role'] != 'libraries':
        continue
    token = fragment['fragment']
    if token.startswith('-'):
        if token not in ('-lstdc++', '-lm'):
            raise RuntimeError('Unreviewed library token: ' + token)
        libraries.append(token)
        continue
    source = Path(token.strip('"').replace('\\', '/'))
    if not source.is_absolute():
        source = binary / source
    if source.name in ('libcorerun_static.a', 'libcoreclr_gen_static.a'):
        excluded.append({'path': str(source), 'reason': 'Own host and complete fresh application helpers replace this input.'})
        continue
    installed = kit / source.name
    if not source.is_file() or not installed.is_file() or digest(source) != digest(installed):
        raise RuntimeError('Actual native graph/installed kit mismatch: ' + str(source))
    libraries.append(installed.as_posix())
    library_files.append(installed)
    archive_provenance.append({'actual_graph_source': str(source), 'installed_kit': str(installed),
                               'sha256': digest(installed), 'bytes': installed.stat().st_size})
backtrace = target['backtraceGraph']
platform_options = []
for fragment in target['link']['commandFragments']:
    if fragment['role'] != 'flags' or 'backtrace' not in fragment:
        continue
    node = backtrace['nodes'][fragment['backtrace']]
    file = backtrace['files'][node['file']].replace('\\', '/')
    if file.endswith('eng/native/configureplatform.cmake'):
        platform_options.append(fragment['fragment'])
expected_required = ['-pthread', '-m64', '-fexceptions', '-sDISABLE_EXCEPTION_CATCHING=0', '-sSUPPORT_LONGJMP=emscripten']
if any(flag in ' '.join(platform_options) for flag in ['-fwasm-exceptions', '-nostdlib', 'wasmexcept', '-l:crt']):
    raise RuntimeError('JS profile unexpectedly inherits native EH or corerun-owned startup policy')
if not all(value in platform_options for value in expected_required):
    raise RuntimeError('Actual platform interface does not establish the required native profile')
cache = {}
for line in (binary / 'CMakeCache.txt').read_text().splitlines():
    if line and not line.startswith(('#', '//')) and '=' in line and ':' in line.split('=', 1)[0]:
        name, value = line.split('=', 1)
        cache[name.split(':', 1)[0]] = value
if cache.get('CLI_CMAKE_COMMIT_HASH') != '1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791' or cache.get('FEATURE_INTERPRETER') != '1' or cache.get('FEATURE_MULTITHREADING', '').upper() in ('1','ON','TRUE'):
    raise RuntimeError('Native source/managed threading profile mismatch')
props = json.loads((kit / 'wasm-props.json').read_text())
expected_props = {'RuntimeWasmNativePthreads':'true', 'RuntimeCoreClrBrowserJsEh':'true', 'RuntimeWasmExceptionModel':'emscripten', 'RuntimeWasmAssemblyFormat':'raw-pe', 'RuntimeWasmInterpreterOnly':'true', 'RuntimeWasmReadyToRun':'false', 'RuntimeWasmWebcil':'false'}
if any(props['Properties'].get(k) != v for k,v in expected_props.items()):
    raise RuntimeError('Installed kit does not declare native pthread compatibility')
compile_options = ['-m64', '-pthread', '-fexceptions', '-msimd128']
helper_definitions = ['GEN_PINVOKE=1', 'TARGET_WASM', 'TARGET_WASM64', 'TARGET_64BIT', 'TARGET_POINTER_SIZE=8']
helper_options = compile_options + ['-include', (kit / 'include/coreclr_compat.h').as_posix()]
host_includes = [repo / 'src/coreclr/hosts/inc', repo / 'src/native/corehost']
browser = [kit / 'libSystem.Native.Browser.js', kit / 'libSystem.Native.Browser.Utils.js']
host_link_options = platform_options + ['-Wl,--gc-sections', '-sINITIAL_MEMORY=134217728',
    '-sMAXIMUM_MEMORY=8589934592', '-sALLOW_MEMORY_GROWTH=1', '-sGROWABLE_ARRAYBUFFERS=0',
    '-sALLOW_TABLE_GROWTH=1', '-sSTACK_SIZE=5MB', '-sEXIT_RUNTIME=1', '-sENVIRONMENT=node,web,worker',
    '-sEXPORTED_RUNTIME_METHODS=' + cache['CMAKE_EMCC_EXPORTED_RUNTIME_METHODS']]
cmake = ['# Cache-only guest target data from the actual successful 1e9f JS-EH native graph.',
         'set(DIRECT_PE_RUNTIME_SINGLE_THREADED true)',
         'set(DIRECT_PE_RUNTIME_EXCEPTION_MODEL emscripten)',
         'set(DIRECT_PE_INTERPRETER_ONLY ON)',
         'set(DIRECT_PE_READY_TO_RUN OFF)',
         'set(DIRECT_PE_NATIVE_CORELIB_SHA256 "' + digest(product / 'IL/System.Private.CoreLib.dll') + '")']
def emit(name, values):
    cmake.append('set(' + name)
    for value in values:
        value = str(value).replace('\\', '/')
        if '"' in value or ';' in value or '\n' in value:
            raise RuntimeError('Unrepresentable CMake profile value')
        cmake.append('    "' + value + '"')
    cmake.append(')')
emit('DIRECT_PE_RUNTIME_LIBRARY_FILES', list(dict.fromkeys(library_files)))
emit('DIRECT_PE_RUNTIME_LINK_INPUTS', libraries)
emit('DIRECT_PE_HOST_INCLUDE_DIRS', host_includes)
emit('DIRECT_PE_HELPER_INCLUDE_DIRS', [kit / 'include'])
emit('DIRECT_PE_HELPER_DEFINITIONS', helper_definitions)
emit('DIRECT_PE_HELPER_COMPILE_OPTIONS', helper_options)
emit('DIRECT_PE_HOST_COMPILE_OPTIONS', compile_options)
emit('DIRECT_PE_HOST_LINK_OPTIONS', host_link_options)
emit('DIRECT_PE_BROWSER_LIBRARIES', browser)
(output / 'native64-profile.cmake').write_text('\n'.join(cmake) + '\n')
headers = list((kit / 'include').rglob('*.h')) + list((kit / 'include').rglob('*.hpp')) + [host_includes[0] / 'coreclrhost.h', host_includes[1] / 'host_runtime_contract.h']
provenance = {'scope': 'Normal independent DirectPeGuest CMake data interface. Actual File API link-library order and repetitions retained; corerun/frameworkgen replaced. No RSP executed, imported or used as the host link command.',
    'source_revision': cache['CLI_CMAKE_COMMIT_HASH'], 'file_api_target': query['corerun_target'],
    'file_api_target_sha256': query['corerun_target_sha256'], 'ordered_libraries': libraries,
    'archive_sources': archive_provenance, 'excluded': excluded, 'platform_link_options': platform_options,
    'user_compile_interface_source': str(repo / 'src/coreclr/hosts/corerun/CMakeLists.txt'),
    'user_compile_interface_source_sha256': digest(repo / 'src/coreclr/hosts/corerun/CMakeLists.txt'),
    'kit_producer_source': str(repo / 'src/coreclr/hosts/corerun/wasm/testkit.cmake'),
    'kit_producer_source_sha256': digest(repo / 'src/coreclr/hosts/corerun/wasm/testkit.cmake'),
    'native_profile_manifest': {'path': str(kit / 'wasm-props.json'), 'sha256': digest(kit / 'wasm-props.json')},
    'headers': {str(path): digest(path) for path in headers}, 'production_js': {str(path): digest(path) for path in browser},
    'host_specific_choices': {'entry': 'own main/real coreclr host contract', 'fs': 'preloaded loose PE, default filesystem; UE lane later requires its existing WasmFS',
                            'exports': 'own application main/malloc/free/exit/shutdown', 'environment': 'node,web,worker'},
    'corerun_host_options_not_adopted': ['CORERUN','NODERAWFS','nodefs.js','libCorerun.js','libCorerun.extpost.js','createDotnetRuntime'],
    'exception_model':'emscripten', 'interpreter_only':True, 'ready_to_run':False, 'compile_options':compile_options, 'host_link_options':host_link_options, 'profile_sha256': digest(output / 'native64-profile.cmake')}
(output / 'native64-profile-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
print(json.dumps({'ordered_library_entries': len(libraries), 'unique_archive_count': len(set(library_files)), 'excluded': excluded,
                  'platform_options': platform_options, 'profile_sha256': provenance['profile_sha256']}, indent=2))
