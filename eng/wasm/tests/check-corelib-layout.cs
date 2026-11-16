// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#:property ImportDirectoryBuildProps=false
#:property ImportDirectoryBuildTargets=false
#:property TargetFramework=net12.0

// Use the repository-pinned SDK:
// dotnet run --file check-corelib-layout.cs -- <wasm-Release-IL> <wasm-Checked-IL> <wasm64-Release-IL> <wasm64-Checked-IL>
// All four CoreLib products are required. Only metadata is read; no guest assembly is loaded or executed.

using System;
using System.Buffers.Binary;
using System.IO;
using System.Linq;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

try
{
    if (args.Length != 4)
        throw new ArgumentException("Pass four CoreLib IL paths in this order: wasm Release, wasm Checked, wasm64 Release, wasm64 Checked.");

    if (args.Select(Path.GetFullPath).Distinct(StringComparer.Ordinal).Count() != 4)
        throw new ArgumentException("Pass four distinct target/configuration product paths.");

    for (int i = 0; i < args.Length; i++)
    {
        int pointerSize = i < 2 ? 4 : 8;
        bool isChecked = (i & 1) != 0;
        CheckCoreLib(args[i], pointerSize);
        Console.WriteLine($"PASS: wasm{pointerSize * 8} {(isChecked ? "Checked" : "Release")} CoreLib native-integer width: {Path.GetFullPath(args[i])}");
    }

    Console.WriteLine("PASS: all 4 required CoreLib products checked; 0 skipped.");
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception.Message);
    return 1;
}

static void CheckCoreLib(string path, int pointerSize)
{
    using FileStream stream = File.OpenRead(path);
    using PEReader pe = new(stream);
    MetadataReader reader = pe.GetMetadataReader();
    if (reader.GetString(reader.GetAssemblyDefinition().Name) != "System.Private.CoreLib")
        throw new InvalidDataException($"'{path}' is not System.Private.CoreLib.");

    foreach (string name in new[] { "IntPtr", "UIntPtr" })
    {
        TypeDefinition type = FindType(reader, "System", name);
        MethodDefinition method = type.GetMethods().Select(reader.GetMethodDefinition)
            .Single(method => reader.GetString(method.Name) == "get_Size");
        byte[] il = pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()!;
        Equal(pointerSize, ReadConstantReturn(il), $"{path}: System.{name}.get_Size()");
    }


}

static TypeDefinition FindType(MetadataReader reader, string ns, string name)
{
    foreach (TypeDefinitionHandle handle in reader.TypeDefinitions)
    {
        TypeDefinition type = reader.GetTypeDefinition(handle);
        if (reader.GetString(type.Namespace) == ns && reader.GetString(type.Name) == name)
            return type;
    }
    throw new InvalidDataException($"CoreLib type '{ns}.{name}' was not found.");
}

static int ReadConstantReturn(byte[] il)
{
    int position = 0;
    SkipNops(il, ref position);
    byte instruction = il[position++];
    int value;
    if (instruction is >= 0x16 and <= 0x1e) // ldc.i4.0 ... ldc.i4.8
    {
        value = instruction - 0x16;
    }
    else if (instruction == 0x1f) // ldc.i4.s
    {
        value = (sbyte)il[position++];
    }
    else if (instruction == 0x20) // ldc.i4
    {
        value = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(position, 4));
        position += 4;
    }
    else
    {
        throw new InvalidDataException("CoreLib get_Size must return a compile-time integer constant.");
    }

    SkipNops(il, ref position);
    if (position != il.Length - 1 || il[position] != 0x2a) // ret
        throw new InvalidDataException("Unexpected instructions after the CoreLib get_Size constant.");
    return value;
}

static void SkipNops(byte[] il, ref int position)
{
    while (position < il.Length && il[position] == 0)
        position++;
}

static void Equal(int expected, int actual, string subject)
{
    if (expected != actual)
        throw new InvalidDataException($"{subject}: expected 0x{expected:x}, actual 0x{actual:x}.");
}
