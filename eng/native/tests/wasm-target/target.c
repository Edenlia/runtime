// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#include <stddef.h>
#include <stdint.h>

_Static_assert(sizeof(void*) == EXPECTED_POINTER_SIZE, "C pointer width must match the selected target");
_Static_assert(sizeof(size_t) == EXPECTED_POINTER_SIZE, "C size_t width must match the selected target");
_Static_assert(sizeof(intptr_t) == EXPECTED_POINTER_SIZE, "C intptr_t width must match the selected target");
