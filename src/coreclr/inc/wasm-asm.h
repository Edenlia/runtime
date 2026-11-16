// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma once

// Pointer operations shared by native assembly and inline assembly. Integer
// payloads, flags, metadata offsets and card bytes keep their own widths.
#ifdef TARGET_WASM64
#define WASM_PTR_TYPE i64
#define WASM_PTR_SIZE 8
#define WASM_PTR_OFFSET2 16
#define WASM_PTR_OFFSET3 24
#define WASM_PTR_CONST i64.const
#define WASM_PTR_LOAD i64.load
#define WASM_PTR_LOAD_U32 i64.load32_u
#define WASM_PTR_ADD i64.add
#define WASM_PTR_IS_NULL i64.eqz
#else
#define WASM_PTR_TYPE i32
#define WASM_PTR_SIZE 4
#define WASM_PTR_OFFSET2 8
#define WASM_PTR_OFFSET3 12
#define WASM_PTR_CONST i32.const
#define WASM_PTR_LOAD i32.load
#define WASM_PTR_LOAD_U32 i32.load
#define WASM_PTR_ADD i32.add
#define WASM_PTR_IS_NULL i32.eqz
#endif

#define WASM_ASM_STRINGIFY_INNER(value) #value
#define WASM_ASM_STRINGIFY(value) WASM_ASM_STRINGIFY_INNER(value)
#define WASM_PTR_TYPE_STR WASM_ASM_STRINGIFY(WASM_PTR_TYPE)

#ifdef TARGET_WASM64
#define WASM_PTR_STORE_STR "i64.store"
#define WASM_PTR_SUB_STR "i64.sub"
#define WASM_PTR_SHR_U_STR "i64.shr_u"
#define WASM_PTR_LT_U_STR "i64.lt_u"
#define WASM_PTR_GE_U_STR "i64.ge_u"
#else
#define WASM_PTR_STORE_STR "i32.store"
#define WASM_PTR_SUB_STR "i32.sub"
#define WASM_PTR_SHR_U_STR "i32.shr_u"
#define WASM_PTR_LT_U_STR "i32.lt_u"
#define WASM_PTR_GE_U_STR "i32.ge_u"
#endif

#define WASM_PTR_CONST_STR WASM_ASM_STRINGIFY(WASM_PTR_CONST)
#define WASM_PTR_LOAD_STR WASM_ASM_STRINGIFY(WASM_PTR_LOAD)
#define WASM_PTR_ADD_STR WASM_ASM_STRINGIFY(WASM_PTR_ADD)
