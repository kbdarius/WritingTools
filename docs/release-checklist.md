# Writing Tools release checklist

Use this before delivering a new build or release.

1. Bump `Windows_and_Linux/version.py` using semantic versioning.
2. Rebuild with `build-windows.bat`.
3. Confirm the output is a versioned file such as `Writing Tools v<version>.exe`.
4. Commit the release changes.
5. Push the completed release to the GitHub `main` branch.

If anything changes in the build flow, update `docs/build-and-release-windows.md` at the same time.
