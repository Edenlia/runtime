// CACHE-ONLY SOURCE CANDIDATE. Build only against the final matching JS-EH product.
using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

[assembly: DisableRuntimeMarshalling]

namespace DirectPeGuest;

public static class EntryPoints
{
    [DllImport("DirectPeGuestNative", EntryPoint = "DirectPeGuest_NativeRoundtrip", CallingConvention = CallingConvention.Cdecl)]
    private static extern int NativeRoundtrip(int value);

    // Keep the original actual PInvoke/UCO/native callback contract intact.
    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    public static int Run(int value) => NativeRoundtrip(value) + 11;

    private sealed class Primary(int value) : Exception("Primary")
    {
        public int Value { get; } = value;
    }
    private sealed class Resumption(Exception inner) : Exception("Resumption", inner) { }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ThrowPrimary(Primary exception) => throw exception;

    private static bool Filter(Primary exception, int expected, ref int count)
    {
        ++count;
        return exception.Value == expected;
    }

    // The normal native host must create this real managed delegate and require
    // 31 for both 9 and -17. Exceptions are contained within the managed entry;
    // no exception is deliberately sent across a precompiled UE native frame.
    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    public static int RunExceptionProof(int value)
    {
        int flags = 0, finallyCount = 0, filterCount = 0;
        var original = new Primary(value);
        try
        {
            try
            {
                try
                {
                    ThrowPrimary(original);
                }
                finally { ++finallyCount; }
            }
            catch (Primary exception) when (Filter(exception, value, ref filterCount))
            {
                if (!ReferenceEquals(exception, original)) return -101;
                flags |= 1; // Correct typed catch and interpreter catch entry.
                throw new Resumption(exception); // Throw a new type from catch.
            }
        }
        catch (Resumption exception)
        {
            if (!ReferenceEquals(exception.InnerException, original)) return -102;
            flags |= 2;
        }
        catch { return -103; }

        // Execution really continues after the catch. Nested throw; must keep
        // the same exception object and run both intervening finally clauses.
        try
        {
            try
            {
                try { ThrowPrimary(original); }
                catch (Primary exception)
                {
                    if (!ReferenceEquals(exception, original)) return -104;
                    throw;
                }
                finally { ++finallyCount; }
            }
            finally { ++finallyCount; }
        }
        catch (Primary exception)
        {
            if (!ReferenceEquals(exception, original) || exception.Value != value) return -105;
            flags |= 4;
        }
        catch { return -106; }
        if (finallyCount == 3) flags |= 8;
        if (filterCount == 1) flags |= 16;
        return flags;
    }
}
