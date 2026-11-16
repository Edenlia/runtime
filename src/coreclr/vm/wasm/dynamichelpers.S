// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#include "asmconstants.h"
#include "wasm-asm.h"

#ifdef TARGET_WASM64
// Let the native compiler lower the final function-pointer operand to its table ABI.
.functype WasmCallGenericDictionaryHelper (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
#define CALL_GENERIC_DICTIONARY_HELPER call WasmCallGenericDictionaryHelper
#else
.tabletype __indirect_function_table, funcref
#define CALL_GENERIC_DICTIONARY_HELPER call_indirect    __indirect_function_table, (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
#endif

.size   g_pClassWithSlotAndModule, WASM_PTR_SIZE
.size   g_pMethodWithSlotAndModule, WASM_PTR_SIZE


.functype       DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull
.globl          DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull
.type           DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull,@function
DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_SizeCheck_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        .local WASM_PTR_TYPE
        block
        block
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SecondIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection
        local.tee       3                                                                       // Store the loaded indirection into local 3, but keep it on the stack as well
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SizeOffset
        WASM_PTR_ADD
        i32.load        0                                                                       // Load the size of the actual GenericDictionary on the Class
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        i32.load        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SlotOffset
        i32.le_s
        br_if           0                                                                       // Branch to the logic to call the helper function if the size of the actual GenericDictionary on the Class is less than or equal to the SlotOffset
        local.get       3                                                                       // Load the SecondDir indirection
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the last indirection
        local.tee       3                                                                       // Store the loaded indirection into local 3, but keep it on the stack as well
#ifdef TARGET_WASM64
        i64.eqz
        i32.eqz
#endif
        br_if           1                                                                       // Branch to return if the result is not null
        end_block
        local.get       0                                                                       // Load the stack pointer
        local.get       1                                                                       // Load the GenericContext
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
        WASM_PTR_CONST       0
        WASM_PTR_LOAD        g_pClassWithSlotAndModule
        local.tee       2
        local.get       2
        WASM_PTR_LOAD        0
        CALL_GENERIC_DICTIONARY_HELPER
        local.set       3
        end_block
        local.get       3                                                                       // Return the result.
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull
.globl          DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull
.type           DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull,@function
DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_SizeCheck_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        .local WASM_PTR_TYPE
        block
        block
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        local.tee       3                                                                       // Store the loaded GenericDictionary into local 3, but keep it on the stack as well
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SizeOffset
        WASM_PTR_ADD
        i32.load        0                                                                       // Load the size of the actual GenericDictionary on the Method
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        i32.load        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SlotOffset
        i32.le_s
        br_if           0                                                                       // Branch to the logic to call the helper function if the size of the actual GenericDictionary on the Method is less than or equal to the SlotOffset
        local.get       3                                                                       // Load the GenericDictionary
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the last indirection
        local.tee       3                                                                       // Store the loaded indirection into local 3, but keep it on the stack as well
#ifdef TARGET_WASM64
        i64.eqz
        i32.eqz
#endif
        br_if           1                                                                       // Branch to return if the result is not null
        end_block
        local.get       0                                                                       // Load the stack pointer
        local.get       1                                                                       // Load the GenericContext
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
        WASM_PTR_CONST       0
        WASM_PTR_LOAD        g_pMethodWithSlotAndModule
        local.tee       2
        local.get       2
        WASM_PTR_LOAD        0
        CALL_GENERIC_DICTIONARY_HELPER
        local.set       3
        end_block
        local.get       3                                                                       // Return the result.
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_TestForNull,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_TestForNull
.globl          DynamicHelper_GenericDictionaryLookup_Class_TestForNull
.type           DynamicHelper_GenericDictionaryLookup_Class_TestForNull,@function
DynamicHelper_GenericDictionaryLookup_Class_TestForNull:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        .local WASM_PTR_TYPE
        block
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SecondIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the last indirection
        local.tee       3                                                                       // Store the loaded indirection into local 3, but keep it on the stack as well
#ifdef TARGET_WASM64
        i64.eqz
        i32.eqz
#endif
        br_if           0                                                                       // Branch to return if the result is not null
        local.get       0                                                                       // Load the stack pointer
        local.get       1                                                                       // Load the GenericContext
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
        WASM_PTR_CONST       0
        WASM_PTR_LOAD        g_pClassWithSlotAndModule
        local.tee       2
        local.get       2
        WASM_PTR_LOAD        0
        CALL_GENERIC_DICTIONARY_HELPER
        local.set       3
        end_block
        local.get       3                                                                       // Return the result.
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class
.globl          DynamicHelper_GenericDictionaryLookup_Class
.type           DynamicHelper_GenericDictionaryLookup_Class,@function
DynamicHelper_GenericDictionaryLookup_Class:
        .functype       DynamicHelper_GenericDictionaryLookup_Class (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SecondIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection
        local.get       2                                                                       // Load the GenericClassDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the last indirection
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class_0_0 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_0_0,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_0_0
.globl          DynamicHelper_GenericDictionaryLookup_Class_0_0
.type           DynamicHelper_GenericDictionaryLookup_Class_0_0,@function
DynamicHelper_GenericDictionaryLookup_Class_0_0:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_0_0 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection (offset 0)
        WASM_PTR_LOAD        0                                                                       // Load the last indirection (offset 0)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class_0_1 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_0_1,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_0_1
.globl          DynamicHelper_GenericDictionaryLookup_Class_0_1
.type           DynamicHelper_GenericDictionaryLookup_Class_0_1,@function
DynamicHelper_GenericDictionaryLookup_Class_0_1:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_0_1 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection (offset 0)
        WASM_PTR_LOAD        WASM_PTR_SIZE                                                                     // Load the last indirection (offset sizeof(TADDR) * 1)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class_0_2 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_0_2,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_0_2
.globl          DynamicHelper_GenericDictionaryLookup_Class_0_2
.type           DynamicHelper_GenericDictionaryLookup_Class_0_2,@function
DynamicHelper_GenericDictionaryLookup_Class_0_2:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_0_2 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection (offset 0)
        WASM_PTR_LOAD        WASM_PTR_OFFSET2                                                                     // Load the last indirection (offset sizeof(TADDR) * 2)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class_0_3 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_0_3,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_0_3
.globl          DynamicHelper_GenericDictionaryLookup_Class_0_3
.type           DynamicHelper_GenericDictionaryLookup_Class_0_3,@function
DynamicHelper_GenericDictionaryLookup_Class_0_3:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_0_3 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__MethodTable__m_pPerInstInfo
        WASM_PTR_LOAD        0                                                                       // Load the SecondDir indirection (offset 0)
        WASM_PTR_LOAD        WASM_PTR_OFFSET3                                                                     // Load the last indirection (offset sizeof(TADDR) * 3)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_TestForNull,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_TestForNull
.globl          DynamicHelper_GenericDictionaryLookup_Method_TestForNull
.type           DynamicHelper_GenericDictionaryLookup_Method_TestForNull,@function
DynamicHelper_GenericDictionaryLookup_Method_TestForNull:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_TestForNull (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        .local WASM_PTR_TYPE
        block
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the last indirection
        local.tee       3                                                                       // Store the loaded indirection into local 3, but keep it on the stack as well
#ifdef TARGET_WASM64
        i64.eqz
        i32.eqz
#endif
        br_if           0                                                                       // Branch to return if the result is not null
        local.get       0                                                                       // Load the stack pointer
        local.get       1                                                                       // Load the GenericContext
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
        WASM_PTR_CONST       0
        WASM_PTR_LOAD        g_pMethodWithSlotAndModule
        local.tee       2
        local.get       2
        WASM_PTR_LOAD        0
        CALL_GENERIC_DICTIONARY_HELPER
        local.set       3
        end_block
        local.get       3                                                                       // Return the result.
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method
.globl          DynamicHelper_GenericDictionaryLookup_Method
.type           DynamicHelper_GenericDictionaryLookup_Method,@function
DynamicHelper_GenericDictionaryLookup_Method:
        .functype       DynamicHelper_GenericDictionaryLookup_Method (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        local.get       2                                                                       // Load the GenericMethodDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD_U32        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
        WASM_PTR_ADD
        WASM_PTR_LOAD        0                                                                       // Load the last indirection
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_0 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_0,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_0
.globl          DynamicHelper_GenericDictionaryLookup_Method_0
.type           DynamicHelper_GenericDictionaryLookup_Method_0,@function
DynamicHelper_GenericDictionaryLookup_Method_0:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_0 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        WASM_PTR_LOAD        0                                                                       // Load the last indirection (offset 0)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_1 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_1,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_1
.globl          DynamicHelper_GenericDictionaryLookup_Method_1
.type           DynamicHelper_GenericDictionaryLookup_Method_1,@function
DynamicHelper_GenericDictionaryLookup_Method_1:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_1 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        WASM_PTR_LOAD        WASM_PTR_SIZE                                                                     // Load the last indirection (offset sizeof(TADDR) * 1)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_2 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_2,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_2
.globl          DynamicHelper_GenericDictionaryLookup_Method_2
.type           DynamicHelper_GenericDictionaryLookup_Method_2,@function
DynamicHelper_GenericDictionaryLookup_Method_2:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_2 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        WASM_PTR_LOAD        WASM_PTR_OFFSET2                                                                     // Load the last indirection (offset sizeof(TADDR) * 2)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_3 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_3,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_3
.globl          DynamicHelper_GenericDictionaryLookup_Method_3
.type           DynamicHelper_GenericDictionaryLookup_Method_3,@function
DynamicHelper_GenericDictionaryLookup_Method_3:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_3 (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       1                                                                       // Load the GenericContext
        WASM_PTR_LOAD        OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
        WASM_PTR_LOAD        WASM_PTR_OFFSET3                                                                     // Load the last indirection (offset sizeof(TADDR) * 3)
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Class_UseHelper (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Class_UseHelper,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Class_UseHelper
.globl          DynamicHelper_GenericDictionaryLookup_Class_UseHelper
.type           DynamicHelper_GenericDictionaryLookup_Class_UseHelper,@function
DynamicHelper_GenericDictionaryLookup_Class_UseHelper:
        .functype       DynamicHelper_GenericDictionaryLookup_Class_UseHelper (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       0                                                                       // Load the stack pointer
        local.get       1                                                                       // Load the GenericContext
        local.get       2                                                                       // Load the GenericDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
        WASM_PTR_CONST       0
        WASM_PTR_LOAD        g_pClassWithSlotAndModule
        local.tee       2
        local.get       2
        WASM_PTR_LOAD        0
        CALL_GENERIC_DICTIONARY_HELPER
        return
        end_function


.functype       DynamicHelper_GenericDictionaryLookup_Method_UseHelper (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
.section        .text.DynamicHelper_GenericDictionaryLookup_Method_UseHelper,"",@
.hidden         DynamicHelper_GenericDictionaryLookup_Method_UseHelper
.globl          DynamicHelper_GenericDictionaryLookup_Method_UseHelper
.type           DynamicHelper_GenericDictionaryLookup_Method_UseHelper,@function
DynamicHelper_GenericDictionaryLookup_Method_UseHelper:
        .functype       DynamicHelper_GenericDictionaryLookup_Method_UseHelper (WASM_PTR_TYPE, WASM_PTR_TYPE, WASM_PTR_TYPE) -> (WASM_PTR_TYPE)
        local.get       0                                                                       // Load the stack pointer
        local.get       1                                                                       // Load the GenericContext
        local.get       2                                                                       // Load the GenericDictionaryDynamicHelperStubData parameter
        WASM_PTR_LOAD        OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
        WASM_PTR_CONST       0
        WASM_PTR_LOAD        g_pMethodWithSlotAndModule
        local.tee       2
        local.get       2
        WASM_PTR_LOAD        0
        CALL_GENERIC_DICTIONARY_HELPER
        return
        end_function
