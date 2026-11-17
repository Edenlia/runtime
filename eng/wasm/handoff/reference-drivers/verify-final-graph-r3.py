from pathlib import Path
import hashlib
import json
import os
import subprocess
ROOT=Path(__file__).resolve().parent
REPO=Path('C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh')
SHA='1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791'
manifest=json.loads((ROOT/'GraphAudit/r3/paths-and-properties.json').read_text())
def norm(path):return os.path.normcase(os.path.normpath(str(path)))
product=REPO/'artifacts/bin/coreclr/browser.wasm64.Release/native-pthreads'
rows=manifest['projects']
checks={'all_six_evaluations_exit0':len(rows)==6 and all(row['exit_code']==0 for row in rows)}
props=[row['evaluation']['Properties'] for row in rows]
checks['all_js_and_native_profile']=all(p['CoreClrBrowserJsEh']=='true' and p['WasmNativePthreads']=='true' for p in props)
checks['no_managed_thread_optin']=all(p.get('WasmEnableThreads','').lower()!='true' and p.get('FeatureMultithreading','').lower()!='true' for p in props)
checks['all_corelib_product_paths_agree']=all(norm(p['CoreclrRuntimeBinDir'])==norm(product) and norm(p['CoreCLRArtifactsPath'])==norm(product) for p in props)
checks['new_canonical_artifacts_only']=all(norm(p['ArtifactsBinDir'])==norm(REPO/'artifacts/bin') and norm(p['ArtifactsObjDir'])==norm(REPO/'artifacts/obj') for p in props)
by_project={row['project']:row for row in rows}
checks['corelib_profile_IL']=norm(by_project['src/coreclr/System.Private.CoreLib/System.Private.CoreLib.csproj']['evaluation']['Properties']['OutputPath'])==norm(product/'IL')
checks['cdac_profile_output']=norm(by_project['src/coreclr/tools/cdac-build-tool/cdac-build-tool.csproj']['evaluation']['Properties']['OutputPath'])==norm(product/'cdac-build-tool')
for name in ('src/coreclr/runtime.proj','src/native/libs/build-native.proj','src/native/corehost/corehost.proj'):
    args=[item['Identity'] for item in by_project[name]['evaluation']['Items']['NativeCMakeArg']]
    checks[name+'_actual_js_cmakearg']=any('CLR_CMAKE_BROWSER_JS_EH=1' in item for item in args)
head=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
status=subprocess.check_output(['git','-C',str(REPO),'-c','core.fsmonitor=false','status','--porcelain'],text=True)
checks['reviewed_clean_source']=head==SHA and not status
report={'source_revision':head,'source_clean':not status,'checks':checks,'passed':all(checks.values()),
        'effective_interpreter_and_runtime_threading':'Must additionally verify actual configured CMakeCache/compile commands after normal graph configure; prebuild MSBuild leaves these inherited defaults empty.',
        'occupancy_receipt':str(ROOT/'pre-final-graph-processes.json'),'normal_driver_sha256':hashlib.sha256((ROOT/'run-normal-native-r3.ps1').read_bytes()).hexdigest()}
(ROOT/'GraphAudit/r3/acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
