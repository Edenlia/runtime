// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

extern alias crossgen2;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

using crossgen2::ILCompiler;
using crossgen2::ILCompiler.DependencyAnalysis;
using crossgen2::ILCompiler.DependencyAnalysis.ReadyToRun;
using crossgen2::ILCompiler.DependencyAnalysis.Wasm;
using crossgen2::ILCompiler.PortableCallHelpers;
using crossgen2::Internal.CallingConvention;
using crossgen2::Internal.JitInterface;

using ILCompiler.ReadyToRun.Tests.TestCasesRunner;

using Internal.TypeSystem;
using Internal.TypeSystem.Ecma;

using Xunit;
using Xunit.Abstractions;

namespace ILCompiler.ReadyToRun.Tests;

/// <summary>
/// Host lowering and generated-source tests for both Wasm widths. The dedicated target-build lane
/// enables the class after building both CoreLibs. Once enabled, missing inputs fail instead of
/// skipping either architecture. These checks do not execute a native or managed Wasm guest.
/// </summary>
[ConditionalClass(typeof(WasmPortableHelperTargetTests), nameof(Enabled))]
public class WasmPortableHelperTargetTests(ITestOutputHelper output)
{
    public static bool Enabled => Environment.GetEnvironmentVariable("WASM64_PORTABLE_HELPER_TESTS") == "1";

    private const string FixtureSource = """
        using System.Runtime.CompilerServices;
        using System.Runtime.InteropServices;
        [assembly: DisableRuntimeMarshalling]
        namespace WidthProbe
        {
            public struct Payload
            {
                public long First;
                public long Second;
            }
            public unsafe class Probe
            {
                [MethodImpl(MethodImplOptions.InternalCall)]
                public extern nint Instance(Payload value, int token);

                [DllImport("portable_width_probe", EntryPoint = "probe_pointer")]
                public static extern nint Import(nint value, ref int token);

                [UnmanagedCallersOnly]
                public static int* Callback(int* value, int token) => value;
            }
        }
        """;

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, 4)]
    [InlineData(TargetArchitecture.Wasm64, 8)]
    public void InstructionSetSelectionPreservesTargetIdentity(TargetArchitecture architecture, int pointerSize)
    {
        var builder = new InstructionSetSupportBuilder(architecture);
        Assert.True(builder.AddSupportedInstructionSet("base"));
        Assert.True(builder.AddSupportedInstructionSet("simd128"));
        Assert.Equal(architecture, builder.Architecture);
        Assert.True(builder.ComputeInstructionSetFlags(0, false, out var supported, out _,
            (required, excluded) => Assert.Fail($"Unexpected ISA conflict: {required}/{excluded}")));
        Assert.True(supported.HasInstructionSet(InstructionSet.Wasm32_WasmBase));
        Assert.True(supported.HasInstructionSet(InstructionSet.Wasm32_PackedSimd));
        ReadyToRunCompilerContext context = CreateContext(architecture);
        Assert.Equal(architecture, context.InstructionSetSupport.Architecture);
        Assert.Equal(pointerSize, context.Target.PointerSize);
        MetadataType vectorDefinition = context.SystemModule.GetType("System.Runtime.Intrinsics"u8, "Vector128`1"u8);
        DefType vector = vectorDefinition.MakeInstantiatedType(context.GetWellKnownType(WellKnownType.Int32));
        Assert.Equal(16, vector.InstanceFieldSize.AsInt);
        Assert.Equal(16, vector.InstanceFieldAlignment.AsInt);
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, 4, "i", "int32_t", "ARG_I32")]
    [InlineData(TargetArchitecture.Wasm64, 8, "l", "int64_t", "ARG_I64")]
    public void NativeSizedTokensAndFixedWidthScalars(
        TargetArchitecture architecture, int pointerSize, string pointerToken, string pointerCType, string pointerArg)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        Assert.Equal(pointerSize, context.Target.PointerSize);
        Assert.Equal(SimdVectorLength.Vector128Bit, context.Target.MaximumSimdVectorLength);

        TypeDesc int32 = context.GetWellKnownType(WellKnownType.Int32);
        TypeDesc[] nativeTypes =
        [
            context.GetWellKnownType(WellKnownType.IntPtr),
            context.GetWellKnownType(WellKnownType.UIntPtr),
            context.GetWellKnownType(WellKnownType.Object),
            int32.MakeArrayType(), int32.MakePointerType(), int32.MakeByRefType(),
            context.GetFunctionPointerType(new MethodSignature(MethodSignatureFlags.Static, 0, int32, [int32])),
        ];
        Assert.All(nativeTypes, type => Assert.Equal(pointerToken, InteropSignature.GetAbiToken(type)));
        Assert.Equal("i", InteropSignature.GetAbiToken(int32));
        Assert.Equal("l", InteropSignature.GetAbiToken(context.GetWellKnownType(WellKnownType.Int64)));

        foreach (string token in new[] { "S16", "A32", "T" })
            Assert.Equal(pointerCType, InteropSignature.TokenToNativeType(token, context.Target));
        Assert.Equal("int32_t", InteropSignature.TokenToNativeType("i", context.Target));
        Assert.Equal("int64_t", InteropSignature.TokenToNativeType("l", context.Target));
        Assert.Equal(pointerArg, InteropSignature.TokenToArgType("T", context.Target));
        Assert.Equal("ARG_I32", InteropSignature.TokenToArgType("i", context.Target));
        Assert.Equal("ARG_I64", InteropSignature.TokenToArgType("l", context.Target));
        Assert.Equal("ARG_IND", InteropSignature.TokenToArgType("S16", context.Target));
        Assert.Equal(2, InteropSignature.TokenToSlotCount("S16"));
        Assert.Equal(4, InteropSignature.TokenToSlotCount("A32"));
        Assert.Throws<LogAsErrorException>(() => InteropSignature.TokenToNativeType("l2", context.Target));
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, "i", "int32_t", "int", "ARG_I32")]
    [InlineData(TargetArchitecture.Wasm64, "l", "int64_t", "int64_t", "ARG_I64")]
    public void ActualMethodSignaturesProduceMatchingPortableFrameDeclarations(
        TargetArchitecture architecture, string pointerToken, string pointerCType, string frameType, string pointerArg)
    {
        WithFixture(architecture, (context, module, _) =>
        {
            EcmaType probe = (EcmaType)module.GetType("WidthProbe"u8, "Probe"u8);
            MethodDesc method = probe.GetMethod("Instance"u8, null);
            string signature = InteropSignature.GetMethodSignature(method);
            Assert.Equal($"{pointerToken}TS16ip", signature);

            var writer = new StringWriter();
            InterpToNativeGenerator.Emit(writer, new Dictionary<string, MethodDesc> { [signature] = method }, context.Target);
            string generated = writer.ToString();
            Assert.Contains($"#define ARG_IND(i) (({pointerCType})(({pointerCType}*)ARG_ADDR(i)))", generated);
            Assert.Contains($"alignas(16) {frameType} framePointer = TERMINATE_R2R_STACK_WALK;", generated);
            Assert.Contains($"{frameType}*, {pointerCType}, {pointerCType}, int32_t, PCODE", generated);
            Assert.Contains($"{pointerArg}(0)", generated);
            Assert.Contains("ARG_IND(1)", generated);
            Assert.Contains("ARG_I32(3)", generated);
            Assert.Contains($"M{signature}", generated);
        });
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, 4)]
    [InlineData(TargetArchitecture.Wasm64, 8)]
    public void ManagedArgumentSlotsUseGuestPointerWidthAndInterpreterSlotSize(TargetArchitecture architecture, int pointerSize)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        TypeDesc int32 = context.GetWellKnownType(WellKnownType.Int32);
        var signature = new MethodSignature(MethodSignatureFlags.Static, 0,
            context.GetWellKnownType(WellKnownType.Void),
            [context.GetWellKnownType(WellKnownType.IntPtr), int32, int32.MakeByRefType()]);
        var (iterator, transition) = GCRefMapBuilder.BuildArgIterator(signature, context);
        Assert.Equal(architecture, transition.Architecture);
        Assert.Equal(pointerSize, transition.PointerSize);
        var offsets = new List<int>();
        int offset;
        while ((offset = iterator.GetNextOffset()) != TransitionBlock.InvalidOffset)
            offsets.Add(offset - transition.OffsetOfArgs);
        Assert.Equal(new[] { 0, 8, 16 }, offsets);
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, 4)]
    [InlineData(TargetArchitecture.Wasm64, 8)]
    public void NativeSizedTransitionWithEightByteArgumentSlots(TargetArchitecture architecture, int pointerSize)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        TypeDesc int32 = context.GetWellKnownType(WellKnownType.Int32);
        var signature = new MethodSignature(MethodSignatureFlags.Static, 0,
            context.GetWellKnownType(WellKnownType.Void),
            [int32, int32.MakePointerType(), context.GetWellKnownType(WellKnownType.Int64), MakeLongTuple(context, 3)]);
        var (iterator, block) = GCRefMapBuilder.BuildArgIterator(signature, context);
        Assert.True(block.IsWasm);
        Assert.Equal(pointerSize, block.PointerSize);
        Assert.Equal(2 * pointerSize, block.OffsetOfArgs);
        Assert.Equal(2 * pointerSize, block.ThisOffset);
        Assert.Equal(2 * pointerSize + 8, block.GetRetBuffArgOffset(hasThis: true));
        Assert.Equal(48, iterator.SizeOfFrameArgumentArray());
        int[] sizes = [4, pointerSize, 8, 24];
        for (int i = 0; i < sizes.Length; i++)
        {
            int offset = iterator.GetNextOffset();
            Assert.Equal(block.OffsetOfArgs + i * 8, offset);
            Assert.Equal(sizes[i], iterator.GetArgSize());
            var location = iterator.GetArgLoc(offset)!.Value;
            Assert.Equal(i * 8, location.m_byteStackIndex);
            Assert.Equal(i == 3 ? 24 : 8, location.m_byteStackSize);
        }
        Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32)]
    [InlineData(TargetArchitecture.Wasm64)]
    public void AggregateAlignmentAndTrailingPointer(TargetArchitecture architecture)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        TypeDesc int32 = context.GetWellKnownType(WellKnownType.Int32);
        DefType vector = context.SystemModule.GetType("System.Runtime.Intrinsics"u8, "Vector128`1"u8)
            .MakeInstantiatedType(int32);
        Assert.Equal(16, vector.InstanceFieldSize.AsInt);
        Assert.Equal(16, vector.InstanceFieldAlignment.AsInt);
        var signature = new MethodSignature(MethodSignatureFlags.Static, 0,
            context.GetWellKnownType(WellKnownType.Void), [int32, vector, int32.MakeByRefType()]);
        var (iterator, block) = GCRefMapBuilder.BuildArgIterator(signature, context);
        Assert.Equal(40, iterator.SizeOfFrameArgumentArray());
        Assert.Equal(block.OffsetOfArgs, iterator.GetNextOffset());
        Assert.Equal(block.OffsetOfArgs + 16, iterator.GetNextOffset());
        Assert.False(iterator.IsArgPassedByRef());
        Assert.Equal(block.OffsetOfArgs + 32, iterator.GetNextOffset());
        Assert.True(iterator.IsArgPassedByRef());
        Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32)]
    [InlineData(TargetArchitecture.Wasm64)]
    public void HiddenArgumentsConsumeSlotsWithoutNamedParameters(TargetArchitecture architecture)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        var signature = new MethodSignature(MethodSignatureFlags.None, 0,
            context.GetWellKnownType(WellKnownType.Void), []);
        var (iterator, block) = GCRefMapBuilder.BuildArgIterator(signature, context,
            methodRequiresInstArg: true, methodIsAsyncCall: true);
        Assert.Equal(24, iterator.SizeOfFrameArgumentArray());
        Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
        Assert.Equal(block.OffsetOfArgs, iterator.GetThisOffset());
        Assert.Equal(block.OffsetOfArgs + 8, iterator.GetParamTypeArgOffset());
        Assert.Equal(block.OffsetOfArgs + 16, iterator.GetAsyncContinuationArgOffset());
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, false)]
    [InlineData(TargetArchitecture.Wasm32, true)]
    [InlineData(TargetArchitecture.Wasm64, false)]
    [InlineData(TargetArchitecture.Wasm64, true)]
    public void AggregateReturnDoesNotInsertReturnBufferArgument(TargetArchitecture architecture, bool hidden)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        TypeDesc int32 = context.GetWellKnownType(WellKnownType.Int32);
        int hiddenSize = hidden ? 24 : 0;
        foreach (int returnSlots in new[] { 1, 3 })
        {
            // These real CoreLib structs exercise 8- and 24-byte returns. The native
            // TARGET_WASM interpreter clears RETURN_HAS_RET_BUFFER for both widths.
            DefType returnType = MakeLongTuple(context, returnSlots);
            var signature = new MethodSignature(hidden ? MethodSignatureFlags.None : MethodSignatureFlags.Static,
                0, returnType, [int32.MakePointerType(), int32]);
            var (iterator, block) = GCRefMapBuilder.BuildArgIterator(signature, context,
                methodRequiresInstArg: hidden, methodIsAsyncCall: hidden);
            Assert.False(iterator.HasRetBuffArg());
            Assert.Equal(hiddenSize + 16, iterator.SizeOfFrameArgumentArray());
            Assert.Equal(block.OffsetOfArgs + hiddenSize, iterator.GetNextOffset());
            Assert.Equal(block.OffsetOfArgs + hiddenSize + 8, iterator.GetNextOffset());
            Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
            if (hidden)
            {
                Assert.Equal(block.OffsetOfArgs, iterator.GetThisOffset());
                Assert.Equal(block.OffsetOfArgs + 8, iterator.GetParamTypeArgOffset());
                Assert.Equal(block.OffsetOfArgs + 16, iterator.GetAsyncContinuationArgOffset());
            }
            var emptySignature = new MethodSignature(signature.Flags, 0, returnType, []);
            var (emptyIterator, _) = GCRefMapBuilder.BuildArgIterator(emptySignature, context,
                methodRequiresInstArg: hidden, methodIsAsyncCall: hidden);
            Assert.False(emptyIterator.HasRetBuffArg());
            Assert.Equal(hiddenSize, emptyIterator.SizeOfFrameArgumentArray());
            Assert.Equal(TransitionBlock.InvalidOffset, emptyIterator.GetNextOffset());
        }
    }

    private static DefType MakeLongTuple(ReadyToRunCompilerContext context, int count)
    {
        MetadataType definition = context.SystemModule.GetType("System"u8,
            System.Text.Encoding.UTF8.GetBytes($"ValueTuple`{count}"));
        DefType tuple = definition.MakeInstantiatedType(new Instantiation(
            Enumerable.Repeat<TypeDesc>(context.GetWellKnownType(WellKnownType.Int64), count).ToArray()));
        Assert.Equal(8 * count, tuple.InstanceFieldSize.AsInt);
        Assert.Equal(8, tuple.InstanceFieldAlignment.AsInt);
        return tuple;
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, "I32")]
    [InlineData(TargetArchitecture.Wasm64, "I64")]
    public void ReverseCallbackPointerNamesMatchTheTarget(TargetArchitecture architecture, string pointerName)
    {
        WithFixture(architecture, (context, module, _) =>
        {
            EcmaMethod callback = (EcmaMethod)module.GetType("WidthProbe"u8, "Probe"u8).GetMethod("Callback"u8, null);
            var writer = new StringWriter();
            var log = new InteropLogger(new Logger(new StringWriter(), isVerbose: false));
            new PInvokeTableGenerator(log).EmitNativeToInterp(writer, [new PInvokeCallback(callback)]);
            string generated = writer.ToString();
            Assert.Contains($"Callback_{pointerName}_I32_Ret{pointerName}", generated);
            Assert.Contains("void * arg0, int32_t arg1", generated);
            Assert.Contains("int64_t args[2]", generated);
        });
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32)]
    [InlineData(TargetArchitecture.Wasm64)]
    public void WholeGeneratorUsesMatchingCoreLibAndIdentifiesMemory64Output(TargetArchitecture architecture)
    {
        WithFixture(architecture, (context, _, workingDirectory) =>
        {
            var options = new PortableCallHelpersGeneratorOptions
            {
                OutputDirectory = Path.Combine(workingDirectory, "generated"),
                TargetOS = "browser",
                PInvokeModules = ["portable_width_probe"],
            };
            var log = new StringWriter();
            Assert.True(PortableCallHelpersGenerator.Run(context, options, new Logger(log, isVerbose: false)) == 0,
                log.ToString());
            string[] files =
            [
                PortableCallHelpersGenerator.PInvokeFileName,
                PortableCallHelpersGenerator.ReversePInvokeFileName,
                PortableCallHelpersGenerator.InterpToNativeFileName,
            ];
            var first = new Dictionary<string, (string Content, DateTime Timestamp)>();
            foreach (string name in files)
            {
                string path = Path.Combine(options.OutputDirectory, name);
                Assert.True(File.Exists(path), path);
                string content = File.ReadAllText(path);
                Assert.NotEmpty(content);
                if (architecture == TargetArchitecture.Wasm64)
                    Assert.Contains("static_assert(sizeof(void*) == 8, \"wasm64 call helpers require 64-bit pointers\");", content);
                else
                    Assert.DoesNotContain("wasm64 call helpers require", content);
                first[name] = (content, File.GetLastWriteTimeUtc(path));
            }
            Assert.Contains("probe_pointer", first[PortableCallHelpersGenerator.PInvokeFileName].Content);
            Assert.Contains("void * probe_pointer (void *, void *);", first[PortableCallHelpersGenerator.PInvokeFileName].Content);
            string pointerName = architecture == TargetArchitecture.Wasm64 ? "I64" : "I32";
            Assert.Contains($"Callback_{pointerName}_I32_Ret{pointerName}", first[PortableCallHelpersGenerator.ReversePInvokeFileName].Content);
            if (architecture == TargetArchitecture.Wasm64)
            {
                string calls = first[PortableCallHelpersGenerator.InterpToNativeFileName].Content;
                foreach (string factory in new[] { "Mllp", "Mlliip", "Mlliilp", "Mliip", "MlS16p" })
                    Assert.Contains($"\"{factory}\"", calls);
                Assert.Contains("CallFunc_S16_RetI64_PE", calls);
                Assert.Contains("int64_t (*fptr)(int64_t*, int64_t, PCODE)", calls);
            }

            Assert.True(PortableCallHelpersGenerator.Run(context, options, new Logger(log, isVerbose: false)) == 0,
                log.ToString());
            foreach (string name in files)
            {
                string path = Path.Combine(options.OutputDirectory, name);
                Assert.Equal(first[name].Content, File.ReadAllText(path));
                Assert.Equal(first[name].Timestamp, File.GetLastWriteTimeUtc(path));
            }
        });
    }

    [Theory]
    [InlineData(TargetArchitecture.Wasm32, "i", "int32_t", "int", 8)]
    [InlineData(TargetArchitecture.Wasm64, "l", "int64_t", "int64_t", 16)]
    public void StringConstructorsUseActualFactorySignaturesWithoutAReceiver(
        TargetArchitecture architecture, string pointerToken, string pointerCType, string frameType, int spanSize)
    {
        ReadyToRunCompilerContext context = CreateContext(architecture);
        TypeDesc character = context.GetWellKnownType(WellKnownType.Char);
        TypeDesc int32 = context.GetWellKnownType(WellKnownType.Int32);
        TypeDesc encoding = context.SystemModule.GetType("System.Text"u8, "Encoding"u8);
        EcmaType stringType = (EcmaType)context.GetWellKnownType(WellKnownType.String);
        DefType span = context.SystemModule.GetType("System"u8, "ReadOnlySpan`1"u8).MakeInstantiatedType(character);
        Assert.Equal(spanSize, span.InstanceFieldSize.AsInt);
        (TypeDesc[] Parameters, string Key, string Declaration)[] cases =
        [
            ([character.MakeArrayType()], pointerToken + pointerToken + "p", $"{pointerCType}"),
            ([character.MakePointerType(), int32, int32], pointerToken + pointerToken + "iip", $"{pointerCType}, int32_t, int32_t"),
            ([character, int32], pointerToken + "iip", "int32_t, int32_t"),
            ([context.GetWellKnownType(WellKnownType.SByte).MakePointerType(), int32, int32, encoding],
                pointerToken + pointerToken + "ii" + pointerToken + "p", $"{pointerCType}, int32_t, int32_t, {pointerCType}"),
            ([span], pointerToken + $"S{spanSize}p", $"{pointerCType}"),
        ];
        var cookies = new Dictionary<string, MethodDesc>();
        foreach (var item in cases)
        {
            MethodDesc constructor = Assert.Single(stringType.GetMethods().Where(method => method.IsConstructor
                && method.Signature.Length == item.Parameters.Length
                && Enumerable.Range(0, item.Parameters.Length).All(index => method.Signature[index] == item.Parameters[index])));
            Assert.True(constructor.IsInternalCall);
            Assert.False(constructor.Signature.IsStatic);
            MethodSignature factory = WasmLowering.GetStringCtorActualSignature(constructor.Signature);
            Assert.True(factory.IsStatic);
            Assert.True(factory.ReturnType.IsWellKnownType(WellKnownType.String));
            Assert.Equal(item.Parameters, Enumerable.Range(0, factory.Length).Select(index => factory[index]).ToArray());
            string signature = WasmLowering.GetSignature(factory, WasmLowering.GetLoweringFlags(constructor)).SignatureString;
            Assert.Equal(item.Key, signature);
            Assert.DoesNotContain("T", signature);
            cookies.Add(signature, constructor);

            var declaration = new StringWriter();
            InterpToNativeGenerator.Emit(declaration, new Dictionary<string, MethodDesc> { [signature] = constructor }, context.Target);
            Assert.Contains($"{pointerCType} (*fptr)({frameType}*, {item.Declaration}, PCODE)", declaration.ToString());
            Assert.Contains($"\"M{signature}\"", declaration.ToString());
            Assert.DoesNotContain("CallFunc_This", declaration.ToString());
        }

        var collector = new InternalCallSignatureCollector(new InteropLogger(new Logger(new StringWriter(), isVerbose: false)));
        collector.ScanType(stringType);
        if (architecture == TargetArchitecture.Wasm64)
        {
            foreach (string key in cookies.Keys)
                Assert.True(collector.Signatures.TryGetValue(key, out MethodDesc? method) && method.IsConstructor, key);
        }
        else
        {
            // Keep the established wasm32 generator output byte-identical.
            Assert.DoesNotContain(collector.Signatures.Values, method => method.IsConstructor);
        }
        Assert.DoesNotContain(collector.Entrypoints, entry => entry.Method.IsConstructor);

        // An ordinary InternalCall may already own the same key as a constructor.
        // Its signature and the static factory must emit exactly the same C call.
        EcmaType handles = (EcmaType)context.SystemModule.GetType("System.Runtime.InteropServices"u8, "GCHandle"u8);
        MethodDesc ordinary = handles.GetMethod("InternalGetWithDebugValidation"u8, null);
        Assert.True(ordinary.IsInternalCall);
        string sharedKey = pointerToken + pointerToken + "p";
        Assert.Equal(sharedKey, InteropSignature.GetMethodSignature(ordinary));
        var collision = new InternalCallSignatureCollector(new InteropLogger(new Logger(new StringWriter(), isVerbose: false)));
        collision.ScanType(handles);
        MethodDesc existing = collision.Signatures[sharedKey];
        Assert.True(existing.IsInternalCall);
        Assert.False(existing.IsConstructor);
        Assert.Equal(sharedKey, InteropSignature.GetMethodSignature(existing));
        collision.ScanType(stringType);
        Assert.Same(existing, collision.Signatures[sharedKey]);
        var ordinaryDeclaration = new StringWriter();
        var factoryDeclaration = new StringWriter();
        InterpToNativeGenerator.Emit(ordinaryDeclaration,
            new Dictionary<string, MethodDesc> { [sharedKey] = collision.Signatures[sharedKey] }, context.Target);
        InterpToNativeGenerator.Emit(factoryDeclaration,
            new Dictionary<string, MethodDesc> { [sharedKey] = cookies[sharedKey] }, context.Target);
        Assert.Equal(factoryDeclaration.ToString(), ordinaryDeclaration.ToString());
    }

    [Fact]
    public void OrdinaryCompilerGeneratesMemory64HelpersWithoutLoadingTheTargetJit()
    {
        WithFixture(TargetArchitecture.Wasm64, (context, _, workingDirectory) =>
        {
            string generatedDirectory = Path.Combine(workingDirectory, "cli-generated");
            var arguments = new List<string>
            {
                "--targetos:browser", "--targetarch:wasm64",
                "--jitpath:" + Path.Combine(workingDirectory, "missing-wasm64-jit.so"),
                "--generate-portable-callhelpers:" + generatedDirectory,
                "--directpinvoke:portable_width_probe",
            };
            arguments.AddRange(context.InputFilePaths.Values);
            R2RCompilationResult result = new R2RDriver(output).Compile(arguments);
            Assert.True(result.Success, result.StandardOutput + result.StandardError);

            string directDirectory = Path.Combine(workingDirectory, "direct-generated");
            var log = new StringWriter();
            Assert.True(PortableCallHelpersGenerator.Run(context, new PortableCallHelpersGeneratorOptions
            {
                OutputDirectory = directDirectory, TargetOS = "browser",
                PInvokeModules = ["portable_width_probe"],
            }, new Logger(log, isVerbose: false)) == 0, log.ToString());

            Assert.Equal(3, Directory.GetFiles(generatedDirectory, "*.cpp").Length);
            foreach (string path in Directory.GetFiles(generatedDirectory, "*.cpp"))
            {
                string content = File.ReadAllText(path);
                Assert.Contains("static_assert(sizeof(void*) == 8, \"wasm64 call helpers require 64-bit pointers\");", content);
                Assert.Equal(File.ReadAllText(Path.Combine(directDirectory, Path.GetFileName(path))), content);
            }
        });
    }

    [Fact]
    public void FullMemory64CompilationIsRejectedBeforeLoadingAJit()
    {
        string workingDirectory = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
        Directory.CreateDirectory(workingDirectory);
        try
        {
            string destination = Path.Combine(workingDirectory, "unexpected-r2r.dll");
            R2RCompilationResult result = new R2RDriver(output).Compile(
            [
                "--targetos:browser", "--targetarch:wasm64", "--out:" + destination,
                "--jitpath:" + Path.Combine(workingDirectory, "missing-wasm64-jit.so"),
                GetCoreLibPath(TargetArchitecture.Wasm64),
            ]);
            Assert.False(result.Success);
            Assert.Contains("ReadyToRun compilation for wasm64 is not supported", result.StandardOutput + result.StandardError);
            Assert.DoesNotContain("Unable to load shared library", result.StandardOutput + result.StandardError);
            Assert.False(File.Exists(destination));
        }
        finally
        {
            Directory.Delete(workingDirectory, recursive: true);
        }
    }

    private ReadyToRunCompilerContext CreateContext(TargetArchitecture architecture, params string[] extraInputs)
    {
        string coreLib = GetCoreLibPath(architecture);
        output.WriteLine($"{architecture} CoreLib: {coreLib}");
        ReadyToRunCompilerContext context = WasmTestHelpers.CreateContextWithCoreLib(
            architecture, TargetOS.Browser, coreLib, extraInputs);
        Assert.Equal(architecture, context.Target.Architecture);
        Assert.Equal(architecture == TargetArchitecture.Wasm64 ? 8 : 4, context.Target.PointerSize);
        Assert.Equal(SimdVectorLength.Vector128Bit, context.Target.MaximumSimdVectorLength);
        return context;
    }

    private void WithFixture(TargetArchitecture architecture, Action<ReadyToRunCompilerContext, EcmaModule, string> action)
    {
        string workingDirectory = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
        Directory.CreateDirectory(workingDirectory);
        try
        {
            string coreLib = GetCoreLibPath(architecture);
            string input = Path.Combine(workingDirectory, "PortableTargetFixture.dll");
            CSharpCompilation compilation = CSharpCompilation.Create(
                "PortableTargetFixture", [CSharpSyntaxTree.ParseText(FixtureSource)],
                [MetadataReference.CreateFromFile(coreLib)],
                new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, allowUnsafe: true));
            var result = compilation.Emit(input);
            Assert.True(result.Success, string.Join(Environment.NewLine,
                result.Diagnostics.Where(diagnostic => diagnostic.Severity == DiagnosticSeverity.Error)));
            ReadyToRunCompilerContext context = CreateContext(architecture, input);
            action(context, context.GetModuleForSimpleName("PortableTargetFixture"), workingDirectory);
        }
        finally
        {
            // The type system holds mapped metadata open. On Windows cleanup is best effort,
            // matching the existing WasmArgumentLayoutTests fixture compilation helpers.
            try { Directory.Delete(workingDirectory, recursive: true); }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { }
        }
    }

    private static string GetCoreLibPath(TargetArchitecture architecture)
    {
        string variable = architecture == TargetArchitecture.Wasm64 ? "WASM64_CORELIB_PATH" : "WASM32_CORELIB_PATH";
        string? path = Environment.GetEnvironmentVariable(variable);
        if (string.IsNullOrEmpty(path))
        {
            DirectoryInfo? repository = new DirectoryInfo(AppContext.BaseDirectory);
            while (repository is not null && !File.Exists(Path.Combine(repository.FullName, "src", "coreclr", "tools", "Common", "TypeSystem", "Common", "TargetArchitecture.cs")))
                repository = repository.Parent;
            Assert.True(repository is not null, $"Set {variable} to matching CoreLib IL when running outside a source checkout.");
            string arch = architecture == TargetArchitecture.Wasm64 ? "wasm64" : "wasm";
            path = Path.Combine(repository!.FullName, "artifacts", "bin", "coreclr",
                $"browser.{arch}.{TestPaths.CoreCLRConfiguration}", "IL", "System.Private.CoreLib.dll");
        }
        path = Path.GetFullPath(path);
        Assert.True(File.Exists(path), $"Missing {architecture} CoreLib: {path}. Build both CoreLib targets; this lane must not skip either width.");
        return path;
    }
}
