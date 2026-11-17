// This bootstraps the actual production Browser/Utils libraries. No dotnet asset
// loader, BrowserHost state, WebCIL registry or replacement CLR service is used.
var dotnetInternals = [{
    Module,
    INTERNAL: {},
    runtimeBuildInfo: { gitHash: "1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791" },
    exit: (code, error) => { throw error || new Error(`direct PE host exit ${code}`); },
}, []];
