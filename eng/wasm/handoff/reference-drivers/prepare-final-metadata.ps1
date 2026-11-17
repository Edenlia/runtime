$ErrorActionPreference = 'Stop'
$profileRoot = $PSScriptRoot
$repo = 'C:/Users/edenlia/Workspace/CodeProjects/runtime-worktrees/eden-web-js-eh'
$guest = Join-Path $profileRoot 'Guest/DirectPeGuest-1e9f8bd1'
$revision = '1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791'
foreach ($name in @('full-native-profile-r3','matching-framework-r3','matching-generator-r3')) {
    $receipt = Get-Content -Raw -LiteralPath (Join-Path $profileRoot "$name-result.json") | ConvertFrom-Json
    if ($receipt.exit_code -ne 0 -or $receipt.source_commit -ne $revision) { throw "No matching successful product: $name" }
}
$component = Get-Content -Raw -LiteralPath (Join-Path $profileRoot 'coreclr-component-r3.json') | ConvertFrom-Json
$corelibPath = "$repo/artifacts/bin/coreclr/browser.wasm64.Release/native-pthreads/IL/System.Private.CoreLib.dll"
$corelibHash = (Get-FileHash -LiteralPath $corelibPath -Algorithm SHA256).Hash.ToLowerInvariant()
$actualNativeCorelibHash = @($component.files.PSObject.Properties | Where-Object Name -Like '*System.Private.CoreLib.dll').Value.sha256
if ($corelibHash -ne $actualNativeCorelibHash) { throw 'Completed native product CoreLib was replaced' }
$framework = "$repo/artifacts/bin/runtime/net12.0-browser-Release-wasm64"
$probePath = Join-Path $guest 'Source/Probe/bin/Release/net12.0/DirectPeGuestProbe.dll'
$frameworkPaths = @($corelibPath) + @(Get-ChildItem -LiteralPath $framework -Filter '*.dll' -File | Sort-Object Name | ForEach-Object FullName)
$records = @{}
foreach ($path in $frameworkPaths + @($probePath)) {
    $stream = [System.IO.File]::OpenRead($path)
    $pe = [System.Reflection.PortableExecutable.PEReader]::new($stream)
    try {
        $md = [System.Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
        $definition = $md.GetAssemblyDefinition()
        $name = $md.GetString($definition.Name)
        $references = @(foreach ($handle in $md.AssemblyReferences) { $reference = $md.GetAssemblyReference($handle); $md.GetString($reference.Name) })
        if ($records.ContainsKey($name)) { throw "Duplicate candidate: $name" }
        $records[$name] = [ordered]@{ name=$name; path=$path; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant(); mvid=$md.GetGuid($md.GetModuleDefinition().Mvid).ToString(); references=$references; ilOnly=[bool]($pe.PEHeaders.CorHeader.Flags -band [System.Reflection.PortableExecutable.CorFlags]::ILOnly); managedNativeHeaderBytes=$pe.PEHeaders.CorHeader.ManagedNativeHeaderDirectory.Size }
    } finally { $pe.Dispose(); $stream.Dispose() }
}
$queue = [System.Collections.Generic.Queue[string]]::new()
$queue.Enqueue('System.Private.CoreLib'); $queue.Enqueue('DirectPeGuestProbe')
$visited = @{}
while ($queue.Count -gt 0) {
    $name = $queue.Dequeue()
    if ($visited.ContainsKey($name)) { continue }
    if (-not $records.ContainsKey($name)) { throw "Missing actual reference: $name" }
    $visited[$name]=$true
    foreach ($reference in $records[$name].references) { $queue.Enqueue($reference) }
}
$inputs = @($visited.Keys | Sort-Object | ForEach-Object { $records[$_] })
$output = Join-Path $guest 'Preparation'
$stage = Join-Path $guest "Stage/$corelibHash/managed"
if (Test-Path -LiteralPath $output) { throw 'Existing final preparation must not be overwritten' }
New-Item -ItemType Directory -Path $output,$stage -Force | Out-Null
foreach ($input in $inputs) {
    if (-not $input.ilOnly -or $input.managedNativeHeaderBytes -ne 0) { throw "Not pure IL: $($input.path)" }
    Copy-Item -LiteralPath $input.path -Destination $stage
}
$metadata = [ordered]@{ phase='Final matching 1e9f JS-EH interpreter-only native product closure; guest not executed'; finalNativeProductClosure=$true; nativeSourceRevision=$revision; nativeGraphReceipt=(Join-Path $profileRoot 'full-native-profile-r3-result.json'); frameworkGraphReceipt=(Join-Path $profileRoot 'matching-framework-r3-result.json'); generatorGraphReceipt=(Join-Path $profileRoot 'matching-generator-r3-result.json'); corelibSha256=$corelibHash; roots=@('System.Private.CoreLib','DirectPeGuestProbe'); candidates=$records.Count; explicitInputs=$inputs; assemblyRefClosureCount=$inputs.Count; stageDirectory=$stage; dynamicReflectionLoads=@(); frameworkCandidates=@($records.Keys | Sort-Object | ForEach-Object { $records[$_] }) }
$metadata | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath (Join-Path $output 'metadata.json') -Encoding utf8
[xml]$modules = Get-Content -Raw -LiteralPath "$repo/eng/wasm/WasmPInvokeModules.props"
$helperManifest = [ordered]@{ InputAssemblies=@($inputs | ForEach-Object path); ReferenceAssemblies=@($records.Keys | Where-Object { -not $visited.ContainsKey($_) } | Sort-Object | ForEach-Object { $records[$_].path }); PInvokeModules=@($modules.Project.ItemGroup.WasmCoreClrFrameworkPInvokeModule | Where-Object Browser -eq 'true' | ForEach-Object Include) + @('DirectPeGuestNative') }
$helperManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'helper-inputs.json') -Encoding utf8
$header = @('static constexpr const char* ManagedFileNames[] = {') + @($inputs | ForEach-Object { '    "' + [System.IO.Path]::GetFileName($_.path) + '",' }) + @('};')
$header | Set-Content -LiteralPath (Join-Path $output 'managed-files.inc') -Encoding ascii
$cmake = @('# Final closure bound to the actual successful native/framework 1e9f JS-EH interpreter-only graphs.', 'set(DIRECT_PE_FINAL_NATIVE_PRODUCT_CLOSURE ON)')
$cmake += 'set(DIRECT_PE_CORELIB "' + $corelibPath.Replace('\','/') + '")'
$cmake += 'set(DIRECT_PE_GENERATED_DIRECTORY "' + $output.Replace('\','/') + '")'
$cmake += 'set(DIRECT_PE_STAGE_DIRECTORY "' + $stage.Replace('\','/') + '")'
$cmake += 'set(DIRECT_PE_STAGE_MANIFEST "' + (Join-Path $output 'metadata.json').Replace('\','/') + '")'
$cmake += 'set(DIRECT_PE_HELPER_SOURCES'
foreach ($name in @('callhelpers-pinvoke.cpp','callhelpers-reverse.cpp','callhelpers-interp-to-managed.cpp')) { $cmake += '    "' + (Join-Path $output "Helpers/$name").Replace('\','/') + '"' }
$cmake += ')'
$cmake | Set-Content -LiteralPath (Join-Path $output 'guest-inputs.cmake') -Encoding utf8
[pscustomobject]$metadata | Select-Object phase,corelibSha256,assemblyRefClosureCount,candidates,stageDirectory | ConvertTo-Json
