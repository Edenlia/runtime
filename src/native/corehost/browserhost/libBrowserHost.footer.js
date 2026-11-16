//! Licensed to the .NET Foundation under one or more agreements.
//! The .NET Foundation licenses this file to you under the MIT license.

/**
 * This is root of **Emscripten library** that would become part of `dotnet.native.js`
 * It implements the corehost and JS related to runtime hosting.
 */

/* eslint-disable no-undef */
function libBrowserHostFactory() {
    // Emscripten executes this factory at link time and serializes library functions.
    // https://emscripten.org/docs/porting/connecting_cpp_and_javascript/Interacting-with-code.html#javascript-limits-in-library-files
    // Link-time Function constructors below preserve compiler macro expansion and
    // signature parsing after Rollup minification. Their functions reach the final
    // output through .toString(); dependencies must be explicitly given to the linker.
    // JS name mangling and minification also applies, see src\native\rollup.config.defines.js and `reserved` there
    // libBrowserHostFn is too complex for acorn-optimizer.mjs to find the dependencies
    // NOTE: wasm_load_icu_data is NOT listed here because it's only available when
    // InvariantGlobalization != true. The loadIcuData() JS code is only called when
    // ICU data is present, so the symbol doesn't need to be a hard link-time dependency.
    let explicitDeps = [
        "BrowserHost_CreateHostContract",
        "BrowserHost_InitializeDotnet",
        "BrowserHost_ExecuteAssembly",
        "BrowserHost_ShutdownDotnet",
    ];
    let commonDeps = [
        "$DOTNET",
        "$ENV",
        "$FS",
        "$libBrowserHostFn",
        "$browserHostNative",
        ...explicitDeps
    ];
    const mergeBrowserHost = {
        $BROWSER_HOST: {
            selfInitialize: () => {
                if (typeof dotnetInternals !== "undefined") {
                    BROWSER_HOST.dotnetInternals = dotnetInternals;

                    const exports = {};
                    libBrowserHostFn(exports);
                    exports.dotnetInitializeModule(dotnetInternals);
                    BROWSER_HOST.exports = exports;
                }
            },
        },
        $libBrowserHostFn: libBrowserHost,
        $BROWSER_HOST__postset: "BROWSER_HOST.selfInitialize()",
        $BROWSER_HOST__deps: commonDeps,
        // Keep this wrapper in place after module initialization so Emscripten's
        // pointer argument conversions are not replaced with the raw TS function.
        BrowserHost_ExternalAssemblyProbe__sig: "ippp",
        BrowserHost_ExternalAssemblyProbe: new Function("pathPtr", "outDataStartPtr", "outSize",
            "return BROWSER_HOST.exports.BrowserHost_ExternalAssemblyProbe(pathPtr, outDataStartPtr, outSize);"),
    };

    let explicitImportsBuilder = "";
    for (const importName of explicitDeps) {
        explicitImportsBuilder += `_${importName}();\n`;
    }
    mergeBrowserHost.$BROWSER_HOST.explicitImports = new Function(explicitImportsBuilder);

    autoAddDeps(mergeBrowserHost, "$BROWSER_HOST");
    // The TS host uses Number heap offsets. Native pointers and size_t arguments
    // use i64 in both MEMORY64=1 and MEMORY64=2; let the compiler own that boundary.
    mergeBrowserHost.$browserHostNative = {
        // Generate at link time, after the Rollup footer has been minified and
        // Emscripten has expanded its macros. Runtime functions contain no macros.
        malloc: new Function("size", "return {{{ from64Expr('_malloc(' + to64('size') + ')') }}};"),
        free: new Function("ptr", "_free({{{ to64('ptr') }}});"),
        posix_memalign: new Function("result", "alignment", "size",
            "return _posix_memalign({{{ to64('result') }}}, {{{ to64('alignment') }}}, {{{ to64('size') }}});"),
        createHostContract: new Function("return {{{ from64Expr('_BrowserHost_CreateHostContract()') }}};"),
        initializeDotnet: new Function("count", "keys", "values",
            "return _BrowserHost_InitializeDotnet(count, {{{ to64('keys') }}}, {{{ to64('values') }}});"),
        executeAssembly: new Function("name", "count", "args",
            "return _BrowserHost_ExecuteAssembly({{{ to64('name') }}}, count, {{{ to64('args') }}});"),
        loadIcuData: new Function("ptr", "return _wasm_load_icu_data({{{ to64('ptr') }}});"),
    };
    mergeBrowserHost.$browserHostNative__deps = ["malloc", "free", "posix_memalign", ...explicitDeps];
    addToLibrary(mergeBrowserHost);
}

libBrowserHostFactory();
