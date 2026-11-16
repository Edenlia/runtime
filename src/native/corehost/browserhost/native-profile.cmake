# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

# Native object compatibility is fixed when the browser host archive is compiled.
# Keep the producer separate so its metadata/install contract can be verified
# without building the runtime's native archives.
set(_browserhost_native_pthreads false)
if(CLR_CMAKE_WASM_NATIVE_PTHREADS)
    set(_browserhost_native_pthreads true)
endif()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/wasm-props.json" CONTENT
    "{\n  \"Properties\": {\n    \"RuntimeWasmNativePthreads\": \"${_browserhost_native_pthreads}\"\n  }\n}\n")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/wasm-props.json" DESTINATION sharedFramework COMPONENT runtime)
