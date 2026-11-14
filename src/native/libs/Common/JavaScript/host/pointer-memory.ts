// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

import { _ems_ } from "../ems-ambient";
import { sizeOfPtr } from "../per-module";

// Typed-array offsets are Numbers even when the native ABI uses i64 pointers.
// Reject inexact conversions rather than silently wrapping to the low 32 bits.
export function pointerToNumber(value: unknown): number {
    if (typeof value !== "number" && typeof value !== "bigint") {
        throw new TypeError("Expected a native pointer");
    }
    const result = Number(value);
    if (!Number.isSafeInteger(result) || result < 0) {
        throw new RangeError("Native pointer cannot be represented exactly as a JavaScript heap offset");
    }
    return result;
}

export function readPointer(address: unknown): number {
    // Acquire the current view on each operation: memory.grow can replace its buffer.
    const view = new DataView(_ems_.HEAPU8.buffer);
    const offset = pointerToNumber(address);
    return sizeOfPtr === 8
        ? pointerToNumber(view.getBigUint64(offset, true))
        : view.getUint32(offset, true);
}

export function writePointer(address: unknown, value: unknown): void {
    const view = new DataView(_ems_.HEAPU8.buffer);
    const offset = pointerToNumber(address);
    const pointer = pointerToNumber(value);
    if (sizeOfPtr === 8) {
        view.setBigUint64(offset, BigInt(pointer), true);
    } else {
        if (pointer > 0xffffffff) {
            throw new RangeError("Native pointer does not fit the Wasm32 ABI");
        }
        view.setUint32(offset, pointer, true);
    }
}
