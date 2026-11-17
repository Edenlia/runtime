"""Create a fresh source-only fixture; no build or old product adoption."""
from pathlib import Path
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parent
RUN=ROOT.parents[1]
OLD=RUN/'RuntimeHost/NativePthreads/Guest/DirectPeGuest-b86/Source'
GUEST=ROOT/'Guest/DirectPeGuest-1e9f8bd1'
SOURCE=GUEST/'Source'
SOURCE.mkdir(parents=True,exist_ok=False)
rows=[]
def copy(relative):
    destination=SOURCE/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OLD/relative,destination)
    rows.append({'source':str(OLD/relative),'destination':str(destination),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()})
for name in ['CMakeLists.txt','host.cpp','bootstrap.js','shutdown-library.js','verify-stage.cmake','Probe/DirectPeGuestProbe.csproj','HelperHost/Program.cs','HelperHost/PortableHelperHost.csproj']:
    copy(name)
managed=ROOT/'GuestSource/Probe/EntryPoints.cs'
shutil.copy2(managed,SOURCE/'Probe/EntryPoints.cs')
rows.append({'source':str(managed),'destination':str(SOURCE/'Probe/EntryPoints.cs'),'sha256':hashlib.sha256(managed.read_bytes()).hexdigest()})
project=SOURCE/'HelperHost/PortableHelperHost.csproj'
project.write_text(project.read_text().replace('eden-web-native-pthreads','eden-web-js-eh'))
host=SOURCE/'host.cpp'
text=host.read_text()
anchor='    const int result = ShutdownRuntime(0);'
if text.count(anchor)!=1:raise RuntimeError('Source host owner-shutdown anchor changed')
text=text.replace(anchor,'''    void* exceptionAddress = nullptr;
    const int exceptionHr = coreclr_create_delegate(State.Handle, State.DomainId,
        "DirectPeGuestProbe", "DirectPeGuest.EntryPoints", "RunExceptionProof", &exceptionAddress);
    std::printf("DIRECT_PE_EXCEPTION_DELEGATE hr=0x%08x address=%p\\n", static_cast<unsigned>(exceptionHr), exceptionAddress);
    if (exceptionHr < 0 || !exceptionAddress) return ShutdownRuntime(7);
    const auto runExceptions = reinterpret_cast<int32_t(*)(int32_t)>(exceptionAddress);
    const int32_t exceptionPositive = runExceptions(9);
    const int32_t exceptionNegative = runExceptions(-17);
    std::printf("DIRECT_PE_MANAGED_EH flagsPositive=%d flagsNegative=%d expected=31\\n", exceptionPositive, exceptionNegative);
    if (exceptionPositive != 31 || exceptionNegative != 31) return ShutdownRuntime(8);
    std::printf("DIRECT_PE_MANAGED_EH_PASS typed=1 newThrowFromCatch=1 rethrow=1 finally=3 filter=1\\n");
''' + anchor)
host.write_text(text)
cmake=SOURCE/'CMakeLists.txt'
text=cmake.read_text()
anchor='include("${DIRECT_PE_GUEST_INPUTS}")'
if text.count(anchor)!=1:raise RuntimeError('Source CMake profile anchor changed')
text=text.replace(anchor,anchor+'''
if(NOT DIRECT_PE_RUNTIME_EXCEPTION_MODEL STREQUAL "emscripten" OR NOT DIRECT_PE_INTERPRETER_ONLY OR DIRECT_PE_READY_TO_RUN)
    message(FATAL_ERROR "This fresh fixture requires the actual interpreter-only JS-EH product.")
endif()
''')
cmake.write_text(text)
repo=Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh')
shutil.copy2(repo/'global.json',GUEST/'global.json')
report={'scope':'Source-only adoption plus new real managed exception delegate checks; no old DLL/helper/metadata/native product reused.',
        'runtime_source_revision':'1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791','source_adoptions':rows,
        'adaptations':['HelperHost references new runtime tree','Managed UCO RunExceptionProof exact return31 for both inputs','Native host requires actual second CLR delegate and its two return31 results before normal owner shutdown','CMake requires actual JS-EH/interpreter-only/non-R2R metadata'],
        'final_source_files':{str(path.relative_to(SOURCE)):hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCE.rglob('*') if path.is_file()},
        'bootstrap_stamp_status':'Old source stamp is deliberately not proof. Replace only from actual completed new Browser/Utils JS before a normal guest build.'}
(GUEST/'source-fixture-provenance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(GUEST)
