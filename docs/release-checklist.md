# Writing Tools release checklist

Use this before delivering a new build or release.

1. Bump `Windows_and_Linux/version.py` using semantic versioning.
2. Rebuild with `build-windows.bat`.
3. Let `build-windows.bat` and its finalizer perform the only release launch. Do not manually start a second copy.
4. Confirm no process is running from an older `Writing Tools v*.exe` path.
5. Confirm the output is a versioned file such as `Writing Tools v<version>.exe` and that it is the only versioned executable remaining in repo root.
6. If an old process or file is locked, stop and resolve it before delivery.
7. Commit the release changes.
8. Push the completed release to the GitHub `main` branch.
9. Provide completion report: repo path, commit hash, version value, build status, and final exe filename.

If anything changes in the build flow, update `docs/build-and-release-windows.md` at the same time.
