#include <coreclrhost.h>
#include <host_runtime_contract.h>
#include <atomic>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "managed-files.inc"

const void* callhelpers_pinvoke_override(const char* library_name, const char* entry_point_name);
extern "C" void DirectPeGuest_BeginShutdown();

namespace {
struct HostState {
    std::map<std::string, std::string> Properties;
    host_runtime_contract Contract{};
    void* Handle = nullptr;
    unsigned int DomainId = 0;
    bool Initialized = false;
    bool Shutdown = false;
    int ShutdownResult = 0;
    int NativeCalls = 0;
    // 0 not started, 1 running, 2 owner shutting down, 3 closed, 4 shutdown failed.
    std::atomic<int> Phase{0};
} State;

size_t HOST_CONTRACT_CALLTYPE GetRuntimeProperty(const char* key, char* buffer, size_t capacity, void* context)
{
    const auto& properties = static_cast<HostState*>(context)->Properties;
    auto found = properties.find(key);
    if (found == properties.end()) return static_cast<size_t>(-1);
    const size_t length = found->second.size() + 1;
    if (buffer && capacity >= length) std::memcpy(buffer, found->second.c_str(), length);
    return length;
}

void RuntimeError(const char* message) { std::fprintf(stderr, "CORECLR_ERROR %s\n", message); }

int ShutdownRuntime(int exitCode)
{
    if (!State.Initialized || State.Shutdown) return State.ShutdownResult ? State.ShutdownResult : exitCode;
    State.Shutdown = true;
    State.Phase.store(2, std::memory_order_release);
    // This runs on the CLR owner thread. Production browser shutdown also stops
    // background timers before coreclr_shutdown_2. Single-threaded CLR shutdown
    // does not pump finalizers at process exit; forced-GC draining is a separate gate.
    DirectPeGuest_BeginShutdown();
    int latchedExitCode = exitCode;
    const int hr = coreclr_shutdown_2(State.Handle, State.DomainId, &latchedExitCode);
    std::printf("DIRECT_PE_SHUTDOWN hr=0x%08x latched=%d\n", static_cast<unsigned>(hr), latchedExitCode);
    // Shutdown may replace the latched code with zero; preserve the primary
    // initializer/delegate/roundtrip failure before considering teardown status.
    State.ShutdownResult = exitCode != 0 ? exitCode : (hr < 0 ? 90 : latchedExitCode);
    State.Phase.store(hr < 0 ? 4 : 3, std::memory_order_release);
    return State.ShutdownResult;
}

bool VerifyLoosePeFiles()
{
    for (const char* name : ManagedFileNames) {
        const std::string path = std::string("/managed/") + name;
        FILE* file = std::fopen(path.c_str(), "rb");
        if (!file) { std::perror(path.c_str()); return false; }
        unsigned char magic[2]{};
        const size_t count = std::fread(magic, 1, sizeof(magic), file);
        std::fclose(file);
        if (count != 2 || magic[0] != 'M' || magic[1] != 'Z') {
            std::fprintf(stderr, "Not a loose PE DLL: %s\n", path.c_str());
            return false;
        }
        std::printf("DIRECT_PE_LOOSE_FILE %s\n", path.c_str());
    }
    return true;
}
}

extern "C" int32_t DirectPeGuest_NativeRoundtrip(int32_t value)
{
    ++State.NativeCalls;
    return value * 3 + 7;
}

// The main-JS exit hook only observes owner-thread shutdown. It must never enter
// a single-threaded CLR instance that was initialized on a proxied pthread.
extern "C" int BrowserHost_ShutdownDotnet(int exitCode)
{
    const int phase = State.Phase.load(std::memory_order_acquire);
    if (phase == 0) return exitCode;
    if (phase != 3 && phase != 4) {
        std::fprintf(stderr, "DIRECT_PE_EXIT_BEFORE_OWNER_SHUTDOWN phase=%d\n", phase);
        return exitCode != 0 ? exitCode : 91;
    }
    return State.ShutdownResult != 0 ? State.ShutdownResult : exitCode;
}

int main()
{
    if (sizeof(void*) != 8) return 2;
    if (!VerifyLoosePeFiles()) return 3;

    // The fixture does not request diagnostic IPC or profiling. These are actual
    // CLR configuration switches, not substituted native diagnostic functions.
    setenv("DOTNET_EnableDiagnostics", "0", 1);
    State.Contract.size = sizeof(State.Contract);
    State.Contract.context = &State;
    State.Contract.get_runtime_property = &GetRuntimeProperty;
    State.Contract.pinvoke_override = &callhelpers_pinvoke_override;

    std::string tpa;
    for (const char* name : ManagedFileNames) {
        if (!tpa.empty()) tpa += ':';
        tpa += std::string("/managed/") + name;
    }
    char contractAddress[2 + sizeof(uintptr_t) * 2 + 1];
    std::snprintf(contractAddress, sizeof(contractAddress), "0x%" PRIxPTR, reinterpret_cast<uintptr_t>(&State.Contract));
    State.Properties = {
        {HOST_PROPERTY_RUNTIME_CONTRACT, contractAddress},
        {HOST_PROPERTY_TRUSTED_PLATFORM_ASSEMBLIES, tpa},
        {HOST_PROPERTY_SYSTEM_CORELIB_DIRECTORY, "/managed"},
        {HOST_PROPERTY_APP_PATHS, "/managed"},
        {HOST_PROPERTY_ENTRY_ASSEMBLY_NAME, "DirectPeGuestProbe"},
        {HOST_PROPERTY_ARGV0, "/managed/DirectPeGuestProbe.dll"},
        {"APP_CONTEXT_BASE_DIRECTORY", "/managed"},
        {"System.Globalization.Invariant", "true"},
        {"System.GC.Concurrent", "false"},
        {"System.GC.Server", "false"},
        {"UnrealSharp.UseAssemblyDependencyResolver", "false"},
    };
    std::vector<const char*> keys, values;
    for (const auto& property : State.Properties) {
        keys.push_back(property.first.c_str());
        values.push_back(property.second.c_str());
    }
    coreclr_set_error_writer(&RuntimeError);
    const int initializeHr = coreclr_initialize("/managed/DirectPeGuestProbe.dll", "DirectPeGuest",
        static_cast<int>(keys.size()), keys.data(), values.data(), &State.Handle, &State.DomainId);
    std::printf("DIRECT_PE_INITIALIZE hr=0x%08x handle=%p domain=%u\n", static_cast<unsigned>(initializeHr), State.Handle, State.DomainId);
    if (initializeHr < 0 || !State.Handle) return 4;
    State.Initialized = true;
    State.Phase.store(1, std::memory_order_release);

    void* address = nullptr;
    const int delegateHr = coreclr_create_delegate(State.Handle, State.DomainId,
        "DirectPeGuestProbe", "DirectPeGuest.EntryPoints", "Run", &address);
    std::printf("DIRECT_PE_CREATE_DELEGATE hr=0x%08x address=%p\n", static_cast<unsigned>(delegateHr), address);
    if (delegateHr < 0 || !address) return ShutdownRuntime(5);
    const auto run = reinterpret_cast<int32_t(*)(int32_t)>(address);
    const int32_t positive = run(9);
    const int32_t negative = run(-17);
    std::printf("DIRECT_PE_ROUNDTRIP positive=%d negative=%d nativeCalls=%d\n", positive, negative, State.NativeCalls);
    if (positive != 45 || negative != -33 || State.NativeCalls != 2) return ShutdownRuntime(6);
    void* exceptionAddress = nullptr;
    const int exceptionHr = coreclr_create_delegate(State.Handle, State.DomainId,
        "DirectPeGuestProbe", "DirectPeGuest.EntryPoints", "RunExceptionProof", &exceptionAddress);
    std::printf("DIRECT_PE_EXCEPTION_DELEGATE hr=0x%08x address=%p\n", static_cast<unsigned>(exceptionHr), exceptionAddress);
    if (exceptionHr < 0 || !exceptionAddress) return ShutdownRuntime(7);
    const auto runExceptions = reinterpret_cast<int32_t(*)(int32_t)>(exceptionAddress);
    const int32_t exceptionPositive = runExceptions(9);
    const int32_t exceptionNegative = runExceptions(-17);
    std::printf("DIRECT_PE_MANAGED_EH flagsPositive=%d flagsNegative=%d expected=31\n", exceptionPositive, exceptionNegative);
    if (exceptionPositive != 31 || exceptionNegative != 31) return ShutdownRuntime(8);
    std::printf("DIRECT_PE_MANAGED_EH_PASS typed=1 newThrowFromCatch=1 rethrow=1 finally=3 filter=1\n");
    const int result = ShutdownRuntime(0);
    if (result == 0) std::printf("DIRECT_PE_GUEST_PASS pointer=%zu\n", sizeof(void*));
    return result;
}
