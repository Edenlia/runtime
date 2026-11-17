"""Layer the measured installed UE threading/FS/memory ABI onto the independent guest."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parent
guest = root / 'Guest/DirectPeGuest-1e9f8bd1'
profile = guest / 'NativeProfile'
ue = Path('C:/Users/edenlia/Epic Games/UE_5.9/Engine/Platforms/Wasm/Source/Programs/UnrealBuildTool')
rules_path = ue / 'WasmTargetRules.cs'
toolchain_path = ue / 'WasmToolChain.cs'
rules = rules_path.read_text()
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
values = {}
for key in ['InitialMemoryMB','MaximumMemoryMB','StackSizeKB','DefaultPthreadStackKB']:
    values[key] = int(re.search(r'public int ' + key + r' = (\d+);', rules).group(1))
for key in ['Malloc','PthreadPoolSize']:
    values[key] = re.search(r'public string ' + key + r' = "([^"\n]+)";', rules).group(1)
if values['MaximumMemoryMB'] != 4096 or values['Malloc'] != 'emmalloc':
    raise RuntimeError('Installed UE defaults changed; review before mapping the standalone profile')
native = (profile / 'native64-profile.cmake').as_posix()
lines = ['# Independent guest UE-compatible ABI/FS/thread lane, not a packaged UE Game.',
         'include("' + native + '")',
         'list(REMOVE_ITEM DIRECT_PE_HOST_LINK_OPTIONS "-sINITIAL_MEMORY=134217728" "-sMAXIMUM_MEMORY=8589934592" "-sSTACK_SIZE=5MB")',
         'list(APPEND DIRECT_PE_HOST_LINK_OPTIONS']
flags = ['-sMEMORY64=2','-sPROXY_TO_PTHREAD','-sWASMFS=1','-sFORCE_FILESYSTEM=1',
         f'-sINITIAL_MEMORY={values["InitialMemoryMB"]}MB', f'-sMAXIMUM_MEMORY={values["MaximumMemoryMB"]}MB',
         f'-sSTACK_SIZE={values["StackSizeKB"]}KB', f'-sDEFAULT_PTHREAD_STACK_SIZE={values["DefaultPthreadStackKB"]}KB',
         '-sMALLOC=' + values['Malloc'], '-sPTHREAD_POOL_SIZE=' + values['PthreadPoolSize'],
         '-sALLOW_BLOCKING_ON_MAIN_THREAD=1','-sABORTING_MALLOC=0','-sDEFAULT_LIBRARY_FUNCS_TO_INCLUDE=$stringToNewUTF8']
for flag in flags:
    if '"' in flag or ';' in flag or '\n' in flag:
        raise RuntimeError('UE default requires explicit CMake serialization review')
    lines.append('    "' + flag + '"')
lines.append(')')
(profile / 'ue-lowered-profile.cmake').write_text('\n'.join(lines) + '\n')
(profile / 'ue-lowered-profile-provenance.json').write_text(json.dumps({
    'scope':'Independent CLR guest with installed UE default lowered-memory/native-pthread/FS/memory/allocator settings; not UE build/game acceptance.',
    'actual_installed_ue_defaults':values, 'rules_source':str(rules_path), 'rules_sha256':digest(rules_path),
    'toolchain_source':str(toolchain_path), 'toolchain_sha256':digest(toolchain_path),
    'native_profile_unchanged_sha256':digest(profile / 'native64-profile.cmake'),
    'appended_link_flags':flags, 'inherited_real_native_compile_flags':['-m64','-pthread','-fexceptions','-msimd128'],
    'profile_sha256':digest(profile / 'ue-lowered-profile.cmake')}, indent=2) + '\n')
print(json.dumps(values, indent=2))
