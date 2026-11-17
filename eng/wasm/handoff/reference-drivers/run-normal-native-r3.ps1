$ErrorActionPreference = 'Stop'
$profileRepo = 'C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh'
$operationRoot = 'C:/Users/edenlia/Workspace/UnrealEngine/CentralParkProjs/.cache/UnrealSharp/Operations/ue-web-support/20261116'
$profileRoot = "$operationRoot/RuntimeHost/JsEh"
$runtimeProduct = "$profileRepo/artifacts/bin/coreclr/browser.wasm64.Release/native-pthreads/"
$buildProperties = @(
    '/m:1',
    '/p:WasmNativePthreads=true',
    '/p:CoreClrBrowserJsEh=true',
    "/p:Memory64IcuDir=$operationRoot/RuntimeHost/NativePthreads/ICU/work/7cb992ff20ba65a7/browser-wasm64/native",
    '/p:BuildSubdirectory=native-pthreads',
    "/p:ArtifactsBinDir=$profileRepo/artifacts/bin/",
    "/p:ArtifactsObjDir=$profileRepo/artifacts/obj/",
    "/p:CoreclrRuntimeBinDir=$runtimeProduct",
    "/p:CoreCLRArtifactsPath=$runtimeProduct",
    "/p:Memory64IcuWorkDir=$profileRoot/ICU/work",
    "/p:Memory64IcuSourceCacheDir=$operationRoot/RuntimeHost/ICU/source-cache",
    "/p:Memory64EmscriptenCacheDir=$profileRoot/EmscriptenCache/6.0.10-fixed-6c5ce14d-js-eh-pthreads",
    "/p:Memory64IcuMsys2Root=$operationRoot/RuntimeHost/Tools/msys64",
    '/p:Memory64IcuMsys2ShortPaths=true',
    '/p:Memory64IcuBuildJobs=2',
    "/bl:$profileRoot/Logs/full-native-profile-r3.binlog",
    '/fl',
    "/flp:logfile=$profileRoot/Logs/full-native-profile-r3.msbuild.log"
)
& "$profileRepo/eng/build.ps1" -subset 'clr.runtime+clr.hosts+clr.corelib+libs.native+host.native' -os browser -arch wasm64 -runtimeFlavor CoreCLR -configuration Release @buildProperties
exit $LASTEXITCODE
