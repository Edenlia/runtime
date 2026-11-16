// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.
// asmconstants.h -
//
// This header defines field offsets and constants used by assembly code
// Be sure to rebuild clr/src/vm/ceemain.cpp after changing this file, to
// ensure that the constants match the expected C/C++ values

#ifndef ASMCONSTANTS_C_ASSERT
#define ASMCONSTANTS_C_ASSERT(cond)
#endif

#ifndef ASMCONSTANTS_RUNTIME_ASSERT
#define ASMCONSTANTS_RUNTIME_ASSERT(cond)
#endif

// Some constants are different in _DEBUG builds.  This macro factors out ifdefs from below.
#ifdef _DEBUG
#define DBG_FRE(dbg,fre) dbg
#else
#define DBG_FRE(dbg,fre) fre
#endif

#include "wasm-asm.h"

#define DynamicHelperFrameFlags_ObjectArg   1
#define DynamicHelperFrameFlags_ObjectArg2  2

#ifdef TARGET_WASM64
#define OFFSETOF__MethodTable__m_pPerInstInfo   DBG_FRE(0x38, 0x30)
#else
#define OFFSETOF__MethodTable__m_pPerInstInfo   DBG_FRE(0x24, 0x20)
#endif
ASMCONSTANTS_C_ASSERT(OFFSETOF__MethodTable__m_pPerInstInfo
                    == offsetof(MethodTable, m_pPerInstInfo));

#ifdef TARGET_WASM64
#define OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo   DBG_FRE(0x48, 0x20)
#else
#define OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo   DBG_FRE(0x28, 0x14)
#endif
ASMCONSTANTS_C_ASSERT(OFFSETOF__InstantiatedMethodDesc__m_pPerInstInfo
                    == offsetof(InstantiatedMethodDesc, m_pPerInstInfo));

#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__stubData WASM_PTR_SIZE
ASMCONSTANTS_C_ASSERT(OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__stubData
                    == offsetof(GenericDictionaryDynamicHelperStubData_PortableEntryPoint, stubData));

#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SecondIndir WASM_PTR_SIZE
ASMCONSTANTS_C_ASSERT(OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SecondIndir
                    == offsetof(GenericDictionaryDynamicHelperStubData, SecondIndir) + offsetof(GenericDictionaryDynamicHelperStubData_PortableEntryPoint, stubData));

#ifdef TARGET_WASM64
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir 0x0C
#else
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir 0x08
#endif
ASMCONSTANTS_C_ASSERT(OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__LastIndir
                    == offsetof(GenericDictionaryDynamicHelperStubData, LastIndir) + offsetof(GenericDictionaryDynamicHelperStubData_PortableEntryPoint, stubData));

#ifdef TARGET_WASM64
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SizeOffset 0x10
#else
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SizeOffset 0x0C
#endif
ASMCONSTANTS_C_ASSERT(OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SizeOffset
                    == offsetof(GenericDictionaryDynamicHelperStubData, SizeOffset) + offsetof(GenericDictionaryDynamicHelperStubData_PortableEntryPoint, stubData));

#ifdef TARGET_WASM64
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SlotOffset 0x14
#else
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SlotOffset 0x10
#endif
ASMCONSTANTS_C_ASSERT(OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__SlotOffset
                    == offsetof(GenericDictionaryDynamicHelperStubData, SlotOffset) + offsetof(GenericDictionaryDynamicHelperStubData_PortableEntryPoint, stubData));

#ifdef TARGET_WASM64
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs 0x18
#else
#define OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs 0x14
#endif
ASMCONSTANTS_C_ASSERT(OFFSETOF__GenericDictionaryDynamicHelperStubData_PortableEntryPoint__HandleArgs
                    == offsetof(GenericDictionaryDynamicHelperStubData, HandleArgs) + offsetof(GenericDictionaryDynamicHelperStubData_PortableEntryPoint, stubData));

#undef ASMCONSTANTS_RUNTIME_ASSERT
#undef ASMCONSTANTS_C_ASSERT
