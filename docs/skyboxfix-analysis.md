# skyboxfix batch analysis

## What the supplied archive contains

The archive has one batch file, `skyboxfix/move.bat`, and six extensionless
files under `skyboxfix/assets/`. The batch was inspected as text and was not
executed.

The batch:

1. Sets its destination to `%LOCALAPPDATA%\Roblox\rbx-storage`.
2. Creates five prefix directories: `a5`, `73`, `6c`, `92`, and `78`.
3. Copies each named asset into a directory matching the first two characters
   of its filename, overwriting an existing file (`copy /Y`).
4. Sets the copied file's Windows read-only attribute (`attrib +R`).
5. Uses no external executable, service, registry change, or administrator
   elevation. Its final `pause` is only a console wait.

The exact filename-to-directory pairs, in batch order, are:

| Cache filename | Directory |
| --- | --- |
| `a564ec8aeef3614e788d02f0090089d8` | `a5` |
| `7328622d2d509b95dd4dd2c721d1ca8b` | `73` |
| `a50f6563c50ca4d5dcb255ee5cfab097` | `a5` |
| `6c94b9385e52d221f0538aadaceead2d` | `6c` |
| `9244e00ff9fd6cee0bb40a262bb35d31` | `92` |
| `78cb2e93aee0cdbd79b15a866bc93a54` | `78` |

Each supplied asset is 1,091 bytes and has the same SHA-256 digest:

`5e710f0e8ff474aa78b2b472e371cb869268c3e033626dc6bca0d33bae704eeb`

The contents begin with Roblox's `RBXH` cache-response marker and contain HTTP
response metadata. The batch does not identify the files as `.tex`, name any
Sky faces, or provide a mapping between those faces and the six cache IDs. It
also does not inspect Roblox version folders.

## v1.0.2 behavior

Polaris implements the evidenced cache root, six exact cache IDs, two-character
subdirectories, and read-only attribute in Python. It does not invoke the
batch. Before changing any target, it records the original contents and file
mode in a separate Polaris backup, writes each file through a temporary file,
checks its SHA-256, and rolls back on an error. Restore puts original files back
and removes files that did not exist before the apply.

The face-to-cache-ID relationship is not present in the supplied archive.
Accordingly, the Custom Sky page does not guess a default mapping. A user must
select a verified one-to-one mapping for all six faces before the Apply button
is enabled. Until an authoritative mapping is available, this is a necessary
manual step, not an inferred fact.

The application stores the detected Roblox version with the apply record. If
the detected version changes, it marks the previous apply as stale. The actual
cache directory remains the global `%LOCALAPPDATA%\Roblox\rbx-storage` path
specified by the supplied batch.

## Validation limits

The source archive provides no `.tex` format specification. Polaris validates
direction names, extensions, duplicate faces/names, non-empty files, size
limits, archive integrity, and the known `RBXH`/gzip envelope when present. It
cannot prove that an arbitrary raw proprietary `.tex` payload is renderable by
Roblox. That requires a format specification or a Windows/Roblox runtime test.
