# Changelog

## GitHub build setup
- Added a Windows GitHub Actions workflow for Python 3.11.
- CI installs development dependencies, runs pytest, builds `Polaris.exe` using `Polaris.spec`, verifies the output, and uploads it as a 14-day artifact.
- Added repository ignore rules for Python caches, test output, and PyInstaller build folders.
- Added Git text line-ending rules for Windows batch files.
