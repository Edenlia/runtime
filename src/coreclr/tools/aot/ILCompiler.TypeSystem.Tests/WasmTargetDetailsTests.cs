// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using Internal.TypeSystem;

using Xunit;

namespace TypeSystemTests
{
    public class WasmTargetDetailsTests
    {
        [Theory]
        [InlineData(TargetArchitecture.Wasm32, 4)]
        [InlineData(TargetArchitecture.Wasm64, 8)]
        public void NativeSizedFieldLayout(TargetArchitecture architecture, int pointerSize)
        {
            // These contexts describe the guest, independently of the architecture running this test.
            var context = new TestTypeSystemContext(architecture, TargetOS.Browser);
            ModuleDesc module = context.CreateModuleForSimpleName("CoreTestAssembly");
            context.SetSystemModule(module);

            Assert.True(context.Target.IsWasm);
            Assert.False(context.Target.SupportsRelativePointers);
            Assert.Equal(pointerSize, context.Target.PointerSize);
            Assert.Equal(pointerSize, context.Target.LayoutPointerSize.AsInt);
            Assert.Equal(pointerSize, context.Target.GetWellKnownTypeSize(context.GetWellKnownType(WellKnownType.IntPtr)).AsInt);
            Assert.Equal(pointerSize, context.Target.GetWellKnownTypeSize(context.GetWellKnownType(WellKnownType.UIntPtr)).AsInt);
            Assert.Equal(4, context.Target.GetWellKnownTypeSize(context.GetWellKnownType(WellKnownType.Int32)).AsInt);
            Assert.Equal(8, context.Target.GetWellKnownTypeSize(context.GetWellKnownType(WellKnownType.Int64)).AsInt);

            MetadataType nativeFields = module.GetType("Sequential"u8, "NativeSizedFields"u8);
            Assert.Equal(pointerSize, nativeFields.InstanceFieldAlignment.AsInt);
            Assert.Equal(4 * pointerSize, nativeFields.InstanceFieldSize.AsInt);
            Assert.Equal(0, nativeFields.GetField("prefix"u8).Offset.AsInt);
            Assert.Equal(pointerSize, nativeFields.GetField("pointer"u8).Offset.AsInt);
            Assert.Equal(2 * pointerSize, nativeFields.GetField("unsignedPointer"u8).Offset.AsInt);
            Assert.Equal(3 * pointerSize, nativeFields.GetField("token"u8).Offset.AsInt);

            MetadataType referenceFields = module.GetType("Sequential"u8, "ReferenceAndToken"u8);
            Assert.True(referenceFields.ContainsGCPointers);
            Assert.Equal(pointerSize, referenceFields.InstanceFieldAlignment.AsInt);
            Assert.Equal(2 * pointerSize, referenceFields.InstanceFieldSize.AsInt);
            Assert.Equal(0, referenceFields.GetField("reference"u8).Offset.AsInt);
            Assert.Equal(pointerSize, referenceFields.GetField("token"u8).Offset.AsInt);

            // The GC heap uses natural pointer alignment for Memory64; the wasm32 align8
            // flag continues to distinguish its two supported object alignments.
            Assert.Equal(pointerSize, context.Target.GetObjectAlignment(LayoutInt.One).AsInt);
            Assert.Equal(8, context.Target.GetObjectAlignment(new LayoutInt(8)).AsInt);
            Assert.Equal(pointerSize == 4, context.Target.SupportsAlign8);
        }
    }
}
