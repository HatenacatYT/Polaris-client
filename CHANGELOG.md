# Changelog

## Polaris improved package
- Added a startup splash screen using the Polaris app artwork and a fade-in transition for the main window.
- Added persistent accent color selection, including a custom color picker.
- Added a home-screen background image selector and reset action.
- Updated `run.bat` to target Python 3.11 and install dependencies for the current user without creating a virtual environment.
- Clarified setup and visual customization instructions in README.
- Preserved the existing Roblox detection, game library, FastFlag editor, presets, backups, logs, and apply/launch workflow.

## Verification
- `python -m compileall -q polaris`: passed.
- `python -m pytest -q`: 38 passed, 2 skipped.
- Windows/Roblox real-world launch and EXE build were not run in this environment.
