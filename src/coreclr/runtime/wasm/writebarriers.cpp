// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.
//

#ifdef FEATURE_NATIVEAOT
#include "common.h"
#include "gcenv.h"
#include "CommonMacros.inl"
#include "GCMemoryHelpers.inl"
#else
#include <fcall.h>
#include "gchelpers.inl"
#include "gcheaputilities.h"
#endif // FEATURE_NATIVEAOT

#include "wasm-asm.h"

#ifdef FEATURE_MULTITHREADING
#error The current assembly implementation of write barriers assumes single-threaded Wasm
#endif

#ifdef FEATURE_MANUALLY_MANAGED_CARD_BUNDLES
#error The current assembly implementation of write barriers does not implement card bundles
#endif

// To simplify integration with the rest of the codebase and avoid complicating the build
// system, Wasm write barriers are implemented using inline assembly inside C functions, below.
// These write barriers use the Wasm-specific FCDECL2_RAW for a native calling convention instead
// of a managed calling convention (to omit the sp and pep parameters). This reduces code size
// considerably and simplifies the JIT. In order to make it safe to call these write barriers from
// inside of a managed function without manually updating the __stack_pointer global, the barriers
// *must* be implemented without use of the linear memory stack, and the best way to guarantee that
// is to implement the barriers by hand in assembly.

#define ASM_HELPER_2(rettype, funcname, a1, a2) \
    EXTERN_C rettype __attribute__((naked)) F_CALL_CONV funcname(a1, a2)

// Helper to make relevant GC globals and constants visible inside of inline assembly
#define GC_ASM(text) \
    asm(text \
        :: [g_lowest_address] "i" (&g_lowest_address), \
        [g_highest_address] "i" (&g_highest_address), \
        [g_ephemeral_low] "i" (&g_ephemeral_low), \
        [g_ephemeral_high] "i" (&g_ephemeral_high), \
        [g_card_table] "i" (&g_card_table), \
        [card_byte_shift] "i" (card_byte_shift) \
    )

EXTERN_C FCDECL2_RAW(void, RhpAssignRef, Object **dst, Object *ref);
ASM_HELPER_2(void, RhpAssignRef, Object **dst, Object *ref)
{
    GC_ASM(
        /* *dst = ref */
        "local.get 0\n"
        "local.get 1\n"
        WASM_PTR_STORE_STR " 0\n"
        /* if ((ref < ephemeral_low) || (ref >= ephemeral_high)) return */
        "local.get 1\n"
        WASM_PTR_CONST_STR " 0\n" WASM_PTR_LOAD_STR " %[g_ephemeral_low]\n"
        WASM_PTR_LT_U_STR "\n"
        "local.get 1\n"
        WASM_PTR_CONST_STR " 0\n" WASM_PTR_LOAD_STR " %[g_ephemeral_high]\n"
        WASM_PTR_GE_U_STR "\n"
        "i32.or\n"
        "if\n return\n end_if\n"
        /* dst = &g_card_table[(dst >> card_byte_shift)] */
        "local.get 0\n"
        WASM_PTR_CONST_STR " %[card_byte_shift]\n"
        WASM_PTR_SHR_U_STR "\n"
        WASM_PTR_CONST_STR " 0\n"
        WASM_PTR_LOAD_STR " %[g_card_table]\n"
        WASM_PTR_ADD_STR "\n"
        "local.tee 0\n"
        /* if (*dst == 255) return */
        "i32.load8_u 0\n"
        "i32.const 255\n"
        "i32.eq\n"
        "if\n return\n end_if\n"
        /* *dst = 255 */
        "local.get 0\n"
        "i32.const 255\n"
        "i32.store8 0\n"
        "return\n"
    );
}

EXTERN_C FCDECL2_RAW(void, RhpCheckedAssignRef, Object **dst, Object *ref);
ASM_HELPER_2(void, RhpCheckedAssignRef, Object **dst, Object *ref)
{
    GC_ASM(
        /* *dst = ref */
        "local.get 0\n"
        "local.get 1\n"
        WASM_PTR_STORE_STR " 0\n"
        /* if ((dst < lowest) || (dst >= highest)) return */
        "local.get 0\n"
        WASM_PTR_CONST_STR " 0\n" WASM_PTR_LOAD_STR " %[g_lowest_address]\n"
        WASM_PTR_LT_U_STR "\n"
        "local.get 0\n"
        WASM_PTR_CONST_STR " 0\n" WASM_PTR_LOAD_STR " %[g_highest_address]\n"
        WASM_PTR_GE_U_STR "\n"
        "i32.or\n"
        "if\n return\n end_if\n"
        /* if ((ref < ephemeral_low) || (ref >= ephemeral_high)) return */
        "local.get 1\n"
        WASM_PTR_CONST_STR " 0\n" WASM_PTR_LOAD_STR " %[g_ephemeral_low]\n"
        WASM_PTR_LT_U_STR "\n"
        "local.get 1\n"
        WASM_PTR_CONST_STR " 0\n" WASM_PTR_LOAD_STR " %[g_ephemeral_high]\n"
        WASM_PTR_GE_U_STR "\n"
        "i32.or\n"
        "if\n return\n end_if\n"
        /* dst = &g_card_table[(dst >> card_byte_shift)] */
        "local.get 0\n"
        WASM_PTR_CONST_STR " %[card_byte_shift]\n"
        WASM_PTR_SHR_U_STR "\n"
        WASM_PTR_CONST_STR " 0\n"
        WASM_PTR_LOAD_STR " %[g_card_table]\n"
        WASM_PTR_ADD_STR "\n"
        "local.tee 0\n"
        /* if (*dst == 255) return */
        "i32.load8_u 0\n"
        "i32.const 255\n"
        "i32.eq\n"
        "if\n return\n end_if\n"
        /* *dst = 255 */
        "local.get 0\n"
        "i32.const 255\n"
        "i32.store8 0\n"
        "return\n"
    );
}
