# Writing Tools release checklist

Use this before delivering a new build or release.

1. Bump `Windows_and_Linux/version.py` using semantic versioning.
2. Rebuild with `build-windows.bat`.
3. Confirm `build-windows.bat` finished by deleting old `Writing Tools v*.exe` files and launching the new one.
4. Confirm the output is a versioned file such as `Writing Tools v<version>.exe` and that it is the only versioned executable remaining in repo root.
5. Commit the release changes.
6. Push the completed release to the GitHub `main` branch.

If anything changes in the build flow, update `docs/build-and-release-windows.md` at the same time.
