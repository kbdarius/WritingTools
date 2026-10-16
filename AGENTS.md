# Repository instructions

- `Windows_and_Linux/version.py` is the authoritative Windows/Linux application version.
- Every code change must bump `APP_VERSION` before delivery. Use semantic versioning: patch for fixes, minor for features, and major for incompatible changes.
- Build artifacts must include the version in their filename (`Writing Tools v<version>.exe`).
- For every versioned build, review `Run Writing Tools (Source).bat` and update it if application paths, the Python environment, entry point, or runtime setup changed. The launcher is not tied to an app version, so a version bump alone does not require editing it. Smoke-test the source launcher and close it before starting the packaged build to avoid competing global hotkeys.
- For every release, follow the build steps in `docs/build-and-release-windows.md` end-to-end before reporting completion.
- `build-windows.bat` and `Windows_and_Linux/finalize-windows-build.ps1` launch the finished executable automatically. Do not manually launch another copy after the build.
- Before delivery, stop every older `Writing Tools v*.exe` process on this PC, delete every older versioned executable from the repository root, and verify that only the current versioned executable remains.
- Let the build finalizer launch the new executable; do not manually start a duplicate. Verify that the new version is running before delivery.
- If an old process or executable cannot be stopped or deleted, the release is not complete; resolve the Windows lock or report the blocker instead of handing over the build.
- When creating a new release, commit the release changes and push them to the GitHub `main` branch. Verify that `main` is in sync with `origin/main` and the working tree is clean.
- Release checklist: `docs/release-checklist.md`
- Full Windows build and release runbook: `docs/build-and-release-windows.md`
