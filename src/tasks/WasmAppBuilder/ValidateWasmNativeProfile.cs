// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System;
using System.IO;
using System.Text.Json;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;

namespace Microsoft.WebAssembly.Build.Tasks;

/// <summary>Checks the native ABI baked into the runtime pack before it is reused or relinked.</summary>
public sealed class ValidateWasmNativeProfile : Task
{
    [Required]
    public string ManifestPath { get; set; } = "";

    public bool NativePthreads { get; set; }

    [Output]
    public bool RuntimeNativePthreads { get; private set; }

    public override bool Execute()
    {
        RuntimeNativePthreads = false;
        try
        {
            // A missing manifest or profile key uses the legacy default. The
            // native-pthread profile always requires an explicit true value.
            if (File.Exists(ManifestPath))
            {
                using FileStream stream = File.OpenRead(ManifestPath);
                using JsonDocument manifest = JsonDocument.Parse(stream);
                if (manifest.RootElement.ValueKind != JsonValueKind.Object ||
                    !manifest.RootElement.TryGetProperty("Properties", out JsonElement properties) ||
                    properties.ValueKind != JsonValueKind.Object)
                {
                    Log.LogError($"Runtime pack native profile '{ManifestPath}' does not contain a valid Properties object.");
                    return false;
                }

                if (properties.TryGetProperty("RuntimeWasmNativePthreads", out JsonElement value))
                {
                    if (value.ValueKind != JsonValueKind.String ||
                        !bool.TryParse(value.GetString(), out bool runtimeNativePthreads))
                    {
                        Log.LogError($"Runtime pack native profile '{ManifestPath}' does not contain a valid RuntimeWasmNativePthreads value.");
                        return false;
                    }

                    RuntimeNativePthreads = runtimeNativePthreads;
                }
            }

            if (RuntimeNativePthreads != NativePthreads)
            {
                Log.LogError($"WasmNativePthreads={NativePthreads.ToString().ToLowerInvariant()} does not match the runtime pack's native profile ({RuntimeNativePthreads.ToString().ToLowerInvariant()}). Select a runtime pack built with the requested native profile; application relinking cannot retarget its precompiled objects. Manifest: '{ManifestPath}'.");
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException)
        {
            Log.LogError($"Could not read runtime pack native profile '{ManifestPath}': {exception.Message}");
        }

        return !Log.HasLoggedErrors;
    }
}
