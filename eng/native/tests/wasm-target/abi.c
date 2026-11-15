// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#include <assert.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct { int64_t integer; double real; void* pointer; } Mixed;

_Static_assert(sizeof(void*) == EXPECTED_POINTER_SIZE, "Pointer width must match the selected target");
_Static_assert(sizeof(uintptr_t) == EXPECTED_POINTER_SIZE, "uintptr_t must hold target pointers");
_Static_assert(sizeof(intptr_t) == EXPECTED_POINTER_SIZE, "intptr_t must hold target pointers");
_Static_assert(sizeof(size_t) == EXPECTED_POINTER_SIZE, "size_t must match target pointer width");

__attribute__((noinline)) int64_t scalar(int32_t a, int64_t b, double c, float d)
{
    return a + b + (int64_t)c + (int64_t)d;
}

__attribute__((noinline)) Mixed aggregate(Mixed value, int64_t delta)
{
    value.integer += delta;
    value.real *= 2;
    value.pointer = (char*)value.pointer + 7;
    return value;
}

__attribute__((noinline)) int64_t callback(int64_t (*invoke)(int32_t, int64_t, double, float))
{
    return invoke(11, 0x100000002LL, 13.0, 17.0f);
}

int main(void)
{
    uint8_t data[32] = { 0 };
    Mixed source = { 0x100000001LL, 1.25, data };
    Mixed result = aggregate(source, 0x100000003LL);
    assert(result.integer == 0x200000004LL);
    assert(result.real == 2.5);
    assert(result.pointer == data + 7);
    *(uint8_t*)result.pointer = 0xA5;
    assert(data[7] == 0xA5);

    int64_t (*volatile function_pointer)(int32_t, int64_t, double, float) = scalar;
    int64_t actual = callback(function_pointer);
    assert(actual == 0x10000002bLL);

    printf("{\"pointer\":%zu,\"size_t\":%zu,\"intptr_t\":%zu,\"function_pointer\":%zu,"
           "\"mixed_size\":%zu,\"mixed_align\":%zu,\"mixed_pointer_offset\":%zu,"
           "\"callback_result\":\"%" PRIx64 "\",\"aggregate_integer\":\"%" PRIx64 "\"}\n",
           sizeof(void*), sizeof(size_t), sizeof(intptr_t), sizeof(function_pointer),
           sizeof(Mixed), _Alignof(Mixed), offsetof(Mixed, pointer), actual, result.integer);
    return 0;
}
