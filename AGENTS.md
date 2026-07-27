# Repository instructions

- `Windows_and_Linux/version.py` is the authoritative Windows/Linux application version.
- Every code change must bump `APP_VERSION` before delivery. Use semantic versioning: patch for fixes, minor for features, and major for incompatible changes.
- Build artifacts must include the version in their filename (`Writing Tools v<version>.exe`).
- For every release, follow the build steps in `docs/build-and-release-windows.md` end-to-end before reporting completion.
- When creating a new release, commit the release changes and push the completed release to the GitHub `main` branch.
- Release checklist: `docs/release-checklist.md`
- Full Windows build and release runbook: `docs/build-and-release-windows.md`
