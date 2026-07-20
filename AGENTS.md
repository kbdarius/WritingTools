# Repository instructions

- `Windows_and_Linux/version.py` is the authoritative Windows/Linux application version.
- Every code change must bump `APP_VERSION` before delivery. Use semantic versioning: patch for fixes, minor for features, and major for incompatible changes.
- Build artifacts must include the version in their filename (`Writing Tools v<version>.exe`).
- When creating a new release, commit the release changes and push the completed release to the GitHub `main` branch.
