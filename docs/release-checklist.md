# Writing Tools release checklist

Use this before delivering a new build or release.

1. Bump `Windows_and_Linux/version.py` using semantic versioning.
2. Review `Run Writing Tools (Source).bat`; update it if the source path, Python environment, entry point, or runtime setup changed. A version bump alone does not require a change because the launcher is not version-specific.
3. Smoke-test the source launcher, confirm the tray icon and global hotkey initialize, then exit it before building so it cannot contend with the packaged app's hotkey.
4. Rebuild with `build-windows.bat`.
5. Let `build-windows.bat` and its finalizer perform the only release launch. Do not manually start a second copy.
6. Confirm no process is running from an older `Writing Tools v*.exe` path.
7. Confirm the output is a versioned file such as `Writing Tools v<version>.exe` and that it is the only versioned executable remaining in repo root.
8. If an old process or file is locked, stop and resolve it before delivery.
9. Commit the release changes.
10. Push the completed release to the GitHub `main` branch.
11. Provide completion report: repo path, commit hash, version value, build status, and final exe filename.

Verify the packaged application visibly opens Settings from both the tray menu and the popup's Manage pinned text command. The finalizer must launch this interactive app with normal window mode, not hidden window mode.

If anything changes in the build flow, update `docs/build-and-release-windows.md` at the same time.
