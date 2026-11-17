// Fixture lifecycle only: delegate to the real production timer cleanup on the
// same worker that owns CLR. This does not substitute any CLR service callback.
addToLibrary({
    DirectPeGuest_BeginShutdown__sig: "v",
    DirectPeGuest_BeginShutdown__deps: ["$DOTNET", "$BROWSER_UTILS"],
    DirectPeGuest_BeginShutdown: () => {
        DOTNET.isAborting = true;
        dotnetBrowserUtilsExports.abortBackgroundTimers();
    },
});
