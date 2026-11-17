using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ILCompiler;
using ILCompiler.PortableCallHelpers;
using Internal.TypeSystem;
using Internal.TypeSystem.Ecma;

// Helper-only metadata validation. This executes the existing runtime generator through its public
// API, matching crossgen2's context setup before the --generate-portable-callhelpers early return.
// It does not produce, load, substitute or test a native JIT or a browser runtime.
string manifestPath = Path.GetFullPath(args[0]);
string outputDirectory = Path.GetFullPath(args[1]);
InputManifest manifest = JsonSerializer.Deserialize<InputManifest>(File.ReadAllText(manifestPath))!;
var inputs = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
foreach (string file in manifest.InputAssemblies)
{
    string path = Path.GetFullPath(file);
    string simpleName = AssemblyName.GetAssemblyName(path).Name!;
    if (!inputs.TryAdd(simpleName, path)) throw new Exception($"Duplicate assembly identity: {simpleName}");
}
var references = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
foreach (string file in manifest.ReferenceAssemblies ?? [])
{
    string path = Path.GetFullPath(file);
    string simpleName = AssemblyName.GetAssemblyName(path).Name!;
    if (!inputs.ContainsKey(simpleName)) references.Add(simpleName, path);
}
InstructionSetSupport instructionSets = new(default, default, TargetArchitecture.Wasm64);
TargetDetails target = new(TargetArchitecture.Wasm64, TargetOS.Browser, TargetAbi.NativeAot, instructionSets.GetVectorTSimdVector());
ReadyToRunCompilerContext context = new(target, SharedGenericsMode.CanonicalReferenceTypes,
    bubbleIncludesCoreModule: true, targetAllowsRuntimeCodeGeneration: false, targetIsSingleThreaded: true,
    instructionSets, oldTypeSystemContext: null)
{
    InputFilePaths = inputs,
    ReferenceFilePaths = references,
};
context.SetSystemModule((EcmaModule)context.GetModuleForSimpleName("System.Private.CoreLib"));
Directory.CreateDirectory(outputDirectory);
var provenance = new
{
    validation = "helper-only",
    targetArchitecture = target.Architecture.ToString(),
    targetOS = "Browser",
    target.PointerSize,
    manifestPath,
    generatorAssembly = typeof(PortableCallHelpersGenerator).Assembly.Location,
    generatorSha256 = Hash(typeof(PortableCallHelpersGenerator).Assembly.Location),
    inputs = inputs.OrderBy(kv => kv.Key).Select(kv => new { simpleName = kv.Key, path = kv.Value, sha256 = Hash(kv.Value) }).ToArray(),
    references = references.OrderBy(kv => kv.Key).Select(kv => new { simpleName = kv.Key, path = kv.Value, sha256 = Hash(kv.Value) }).ToArray(),
};
File.WriteAllText(Path.Combine(outputDirectory, "provenance.json"), JsonSerializer.Serialize(provenance, new JsonSerializerOptions { WriteIndented = true }));
int result = PortableCallHelpersGenerator.Run(context, new PortableCallHelpersGeneratorOptions
{
    OutputDirectory = outputDirectory,
    PInvokeModules = manifest.PInvokeModules,
    TargetOS = "browser",
}, new Logger(Console.Out, isVerbose: true));
Console.WriteLine($"Helper-only generator exit: {result}; explicit inputs: {inputs.Count}; references: {references.Count}");
Environment.ExitCode = result;

static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
record InputManifest(string[] InputAssemblies, string[]? ReferenceAssemblies, string[] PInvokeModules);
