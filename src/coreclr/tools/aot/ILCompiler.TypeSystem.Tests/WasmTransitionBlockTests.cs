// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System;
using Internal.CallingConvention;
using Internal.CorConstants;
using Internal.JitInterface;
using Internal.TypeSystem;
using Xunit;

namespace TypeSystemTests
{
    public class WasmTransitionBlockTests
    {
        [Theory]
        [InlineData(TargetArchitecture.Wasm32, 4)]
        [InlineData(TargetArchitecture.Wasm64, 8)]
        public void NativeSizedTransitionWithEightByteArgumentSlots(TargetArchitecture architecture, int pointerSize)
        {
            TransitionBlock block = TransitionBlock.FromTarget(architecture, false, false, false);
            Assert.True(block.IsWasm);
            Assert.Equal(pointerSize, block.PointerSize);
            Assert.Equal(2 * pointerSize, block.OffsetOfArgs);
            Assert.Equal(2 * pointerSize, block.ThisOffset);
            Assert.Equal(2 * pointerSize + 8, block.GetRetBuffArgOffset(hasThis: true));
            var iterator = CreateIterator(block, false,
                new Handle(CorElementType.ELEMENT_TYPE_I4, pointerSize),
                new Handle(CorElementType.ELEMENT_TYPE_PTR, pointerSize),
                new Handle(CorElementType.ELEMENT_TYPE_I8, pointerSize),
                new Handle(CorElementType.ELEMENT_TYPE_VALUETYPE, pointerSize, 24));

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
            Assert.Equal(48, iterator.SizeOfFrameArgumentArray());
        }

        [Theory]
        [InlineData(TargetArchitecture.Wasm32)]
        [InlineData(TargetArchitecture.Wasm64)]
        public void AggregateAlignmentAndTrailingPointer(TargetArchitecture architecture)
        {
            TransitionBlock block = TransitionBlock.FromTarget(architecture, false, false, false);
            var iterator = CreateIterator(block, false,
                new Handle(CorElementType.ELEMENT_TYPE_I4, block.PointerSize),
                new Handle(CorElementType.ELEMENT_TYPE_VALUETYPE, block.PointerSize, 16, 16),
                new Handle(CorElementType.ELEMENT_TYPE_BYREF, block.PointerSize));
            Assert.Equal(block.OffsetOfArgs, iterator.GetNextOffset());
            Assert.Equal(block.OffsetOfArgs + 16, iterator.GetNextOffset());
            Assert.False(iterator.IsArgPassedByRef());
            Assert.Equal(block.OffsetOfArgs + 32, iterator.GetNextOffset());
            Assert.True(iterator.IsArgPassedByRef());
            Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
            Assert.Equal(40, iterator.SizeOfFrameArgumentArray());
        }

        [Theory]
        [InlineData(TargetArchitecture.Wasm32)]
        [InlineData(TargetArchitecture.Wasm64)]
        public void HiddenArgumentsConsumeSlotsWithoutNamedParameters(TargetArchitecture architecture)
        {
            TransitionBlock block = TransitionBlock.FromTarget(architecture, false, false, false);
            var iterator = CreateIterator(block, true);
            Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
            Assert.Equal(24, iterator.SizeOfFrameArgumentArray());
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
            TransitionBlock block = TransitionBlock.FromTarget(architecture, false, false, false);
            int hiddenSize = hidden ? 24 : 0;

            // vm/callingconvention.h explicitly clears RETURN_HAS_RET_BUFFER under
            // TARGET_WASM: even large interpreter struct returns do not add an argument.
            foreach (int returnSize in new[] { 8, 24 })
            {
                var returnType = new Handle(CorElementType.ELEMENT_TYPE_VALUETYPE, block.PointerSize, returnSize);
                var iterator = CreateIteratorWithReturnType(block, hidden, returnType,
                    new Handle(CorElementType.ELEMENT_TYPE_PTR, block.PointerSize),
                    new Handle(CorElementType.ELEMENT_TYPE_I4, block.PointerSize));

                Assert.False(iterator.HasRetBuffArg());
                Assert.Equal(block.OffsetOfArgs + hiddenSize, iterator.GetNextOffset());
                Assert.Equal(block.OffsetOfArgs + hiddenSize + 8, iterator.GetNextOffset());
                Assert.Equal(TransitionBlock.InvalidOffset, iterator.GetNextOffset());
                Assert.Equal(hiddenSize + 16, iterator.SizeOfFrameArgumentArray());

                if (hidden)
                {
                    Assert.Equal(block.OffsetOfArgs, iterator.GetThisOffset());
                    Assert.Equal(block.OffsetOfArgs + 8, iterator.GetParamTypeArgOffset());
                    Assert.Equal(block.OffsetOfArgs + 16, iterator.GetAsyncContinuationArgOffset());
                }

                var emptyIterator = CreateIteratorWithReturnType(block, hidden, returnType);
                Assert.False(emptyIterator.HasRetBuffArg());
                Assert.Equal(TransitionBlock.InvalidOffset, emptyIterator.GetNextOffset());
                Assert.Equal(hiddenSize, emptyIterator.SizeOfFrameArgumentArray());
            }
        }

        private static ArgIterator<Handle> CreateIterator(TransitionBlock block, bool hidden, params Handle[] parameters)
            => CreateIteratorWithReturnType(block, hidden, new Handle(CorElementType.ELEMENT_TYPE_VOID, block.PointerSize), parameters);

        private static ArgIterator<Handle> CreateIteratorWithReturnType(TransitionBlock block, bool hidden, Handle returnType, params Handle[] parameters)
            => new(block,
                new ArgIteratorData<Handle>(hidden, false, parameters, returnType),
                hidden ? CallingConventions.ManagedInstance : CallingConventions.ManagedStatic,
                hasParamType: hidden, hasAsyncContinuation: hidden, extraFunctionPointerArg: false,
                forcedByRefParams: null, skipFirstArg: false, extraObjectFirstArg: false, isWindows: false,
                objectTypeHandle: new Handle(CorElementType.ELEMENT_TYPE_CLASS, block.PointerSize),
                intPtrTypeHandle: new Handle(CorElementType.ELEMENT_TYPE_I, block.PointerSize));

        // The common iterator's metadata-provider contract, without a native JIT dependency.
        private readonly record struct Handle(CorElementType Kind, int PointerSize, int Size = 0, int Alignment = 8) : ITypeHandle
        {
            public bool IsNull() => false;
            public bool IsValueType() => Kind == CorElementType.ELEMENT_TYPE_VALUETYPE;
            public bool IsPointerType() => Kind == CorElementType.ELEMENT_TYPE_PTR;
            public bool HasIndeterminateSize() => false;
            public int GetSize() => Size;
            public CorElementType GetCorElementType() => Kind;
            public bool RequiresAlign8() => false;
            public bool IsHomogeneousAggregate() => false;
            public int GetHomogeneousAggregateElementSize() => throw new InvalidOperationException();
            public void GetSystemVAmd64PassStructInRegisterDescriptor(out SYSTEMV_AMD64_CORINFO_STRUCT_REG_PASSING_DESCRIPTOR descriptor) => throw new InvalidOperationException();
            public FpStructInRegistersInfo GetFpStructInRegistersInfo(TargetArchitecture architecture) => throw new InvalidOperationException();
            public bool IsTrivialPointerSizedStruct() => false;
            public int GetFieldAlignment() => Alignment;
        }
    }
}
