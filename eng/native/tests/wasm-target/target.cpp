// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#include <stddef.h>
#include <stdint.h>
#include "switches.h"

#if !defined(HOST_WASM) || !defined(TARGET_WASM)
#error Both architectures must belong to the Wasm family.
#endif

#if EXPECTED_POINTER_SIZE == 8
#ifdef FEATURE_64BIT_ALIGNMENT
#error The wasm32 special align8 flag must not select a wasm64 layout.
#endif
#if !defined(HOST_WASM64) || !defined(TARGET_WASM64) || !defined(HOST_64BIT) || !defined(TARGET_64BIT)
#error A wasm64 native build must select 64-bit host and target layouts.
#endif
#if defined(HOST_WASM32) || defined(TARGET_WASM32) || defined(HOST_32BIT) || defined(TARGET_32BIT)
#error A wasm64 native build must not select any 32-bit layouts.
#endif
#else
#ifndef FEATURE_64BIT_ALIGNMENT
#error The wasm32 special align8 flag must remain enabled.
#endif
#if !defined(HOST_WASM32) || !defined(TARGET_WASM32) || !defined(HOST_32BIT) || !defined(TARGET_32BIT)
#error A wasm32 native build must select 32-bit host and target layouts.
#endif
#if defined(HOST_WASM64) || defined(TARGET_WASM64) || defined(HOST_64BIT) || defined(TARGET_64BIT)
#error A wasm32 native build must not select any 64-bit layouts.
#endif
#endif

static_assert(sizeof(void*) == EXPECTED_POINTER_SIZE);
static_assert(sizeof(size_t) == EXPECTED_POINTER_SIZE);
static_assert(sizeof(intptr_t) == EXPECTED_POINTER_SIZE);
