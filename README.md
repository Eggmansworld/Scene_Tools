# 🎬 Eggman's Scene Tools

**Version:** 1.1  
**Platform:** Windows (Python 3.10+)  
**GUI:** Tkinter (dark theme, no external UI framework required)

---

A growing collection of utilities for working with **scene releases** — the structured, NFO/SFV-accompanied archive releases distributed by the warez scene. Built around the workflows of RomVault and [dats.site](https://dats.site/home.php), this toolset helps manage DAT files and ZIP archives in a way that keeps data pristine and catalogue-ready.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Tab 1 — Scene Dat Stripper](#tab-1--scene-dat-stripper)
- [Tab 2 — Comment Repair](#tab-2--comment-repair)
- [Shared Features](#shared-features)
- [Logs](#logs)
- [File Output Reference](#file-output-reference)
- [Known Limitations](#known-limitations)

---

## Overview

Eggman's Scene Tools is a single-file Python/Tkinter application that presents multiple tools as tabs within one window. Each tab is self-contained with its own input controls, options, log pane, and action buttons.

The application is designed for users who:

- Maintain structured scene release archives catalogued by RomVault or ClrMamePro
- Use DAT files from sources such as [dats.site](https://dats.site/home.php) to verify and manage their collections
- Want to track scene release metadata without necessarily storing the full RAR data
- Need to repair ZIP files so they validate cleanly against scene DAT entries

---

## Requirements

| Dependency | Required | Purpose |
|---|---|---|
| Python 3.10+ | ✅ Yes | f-strings, `match`, type hints |
| `tkinter` | ✅ Yes | Bundled with standard Python on Windows |
| `tkinterdnd2` | ⚠️ Optional | Enables drag-and-drop onto folder/file pickers |

### Install optional drag-and-drop support

```
pip install tkinterdnd2
```

If `tkinterdnd2` is not installed, the app runs normally — browse buttons and manual path entry work as expected. A warning banner will appear in the header.

---

## Installation

No installer required. Download or clone the repository and run directly:

```
python Eggmans_Scene_Tools.py
```

No `pip install` is needed beyond the optional `tkinterdnd2` above.

---

## Tab 1 — Scene Dat Stripper

### Purpose

Scene releases are distributed as a set of RAR volumes accompanied by support files: an `.nfo` info file, an `.sfv` checksum file, a `.diz` description file, and often proof image files (`.jpg`/`.png`). The actual content (movies, games, software) lives inside the RAR volumes.

A **scene DAT file** (`.dat` or `.xml` in ClrMamePro/RomVault XML format) catalogues every file in every release, including all RAR volumes. For users who only want to track *that a release existed* — without storing the multi-gigabyte RAR data — the DAT as-distributed is too heavy: it demands you have the RAR volumes present before RomVault considers a release complete.

The **Scene Dat Stripper** solves this by processing your DAT/XML files and **removing all `<rom>` entries whose filenames match RAR volume patterns**, leaving only the support file entries (NFO, SFV, DIZ, proofs, etc.). The result is a **skeleton DAT** — a lightweight scene record that lets RomVault or ClrMamePro verify the presence of support files without requiring the actual release data.

This is particularly useful for:

- Users who follow the scene for cataloguing and archival purposes
- Building a verifiable record of releases using only NFO/SFV files
- Reducing DAT complexity for large scene catalogues where full data is not retained

NOTE: This app function does require you to retrieve the original scene dats from the [dats.site](https://dats.site) website. You can do this yourself by:
- visiting the site, 
- selecting a system platform from the dropdown menus,
- click on the download icon.

If the download icon brings you to a "Get Scene DATs" screen with a big red SETTINGS button, it means you have NOT yet setup the site's cookies. There are 8 site setting cookies that will determine how the website will format and configure the dats before you download them.  These are my settings for a typical setup, but you can change it so the dats look any way you want them to.  

1. which DATEFORMAT will be used in the front of Release DIR:
	0 - NO DATE
 
2. You want to use: <clrmamepro forcepacking="unzip"/> in the DAT?
	1 - YES
 
3. Choose how Releases should be sorted in the DATs:
	0 - Alphabetical
 
4. Choose in which direction Releases should be sorted in the DATs:
	0 - ASC (ascending)
 
5. Choose if you want to include NUKED releases or not:
	1 - YES, include
 
6. Choose if you want to include possible P2P releases or not:
	0 - NO, exclude
 
7. Choose if you want that Year Releases are placed into Month Subfolders or not:
	0 - NO, Month Subfolders NOT needed
 
8. Choose if you want that prefix [NUKED] is set in front of your Releasename:
	1 - YES
 

When you've set all 8 cookie settings, it will show you a green "Your Browser Cookies are enabled".  Scroll down and click on "Back to DATs".  You'll now be able to download any of the dats on the site and they will be setup to the preferences you've set.  You can change these options anytime you want to fit your own needs.

You must have cookies enabled in your browser for this site to allow you to download from it.  


Alternately, you can get all these dats from RomVault's DATVAULT, including all updates as they are released.  Subscription required.

---

### What Gets Removed

The stripper targets `<rom name="...">` lines only. A line is removed if the `name` attribute ends in any of the following RAR volume patterns:

| Pattern | Example |
|---|---|
| `.rar` | `release.rar` |
| `.partNN.rar` | `release.part01.rar`, `release.part001.rar` |
| `.r00` – `.r99` | `release.r00`, `release.r47` |
| `.s00` – `.s99` | `release.s00` |
| `.t00` – `.t99` | `release.t00` |
| `.u00` – `.u99` | `release.u00` |
| `.v00` – `.v99` | `release.v00` |
| `.w00` – `.w99` | `release.w00` |
| `.001` – `.999` | `release.001`, `release.023` |

> **`.sfv` files are never removed**, regardless of any other pattern match. SFV files are the scene's primary checksum verification mechanism and are always considered support files.

All other `<rom>` entries (NFO, DIZ, JPG, PNG, SFV, etc.) and all non-`<rom>` XML structure (headers, game blocks, metadata) are left completely untouched. Line endings and encoding are preserved per-file.

---

### Controls

| Control | Description |
|---|---|
| **Source Folder** | Folder to scan recursively for `.dat` and `.xml` files. Supports drag-and-drop if `tkinterdnd2` is installed. |
| **Create .old backup** | Before modifying any file, saves the original as `filename.dat.old`. If a `.old` already exists, a timestamp is appended (`filename.dat.20250101_120000.old`). Recommended. |
| **▶ Run** | Starts the scan in a background thread. The UI remains responsive. |
| **■ Stop** | Requests a graceful stop after the current file finishes processing. |
| **Open Log Folder** | Opens the `logs/` directory beside the script in Windows Explorer. |
| **Save Log** | Saves the visible log pane content to a `.txt` file of your choosing. |
| **Clear Log** | Clears the log pane display (does not affect the file log). |

---

### Log Output

Each file produces one of the following entries in the log:

| Tag | Meaning |
|---|---|
| `[CHANGED]` | File was modified — RAR rom lines were removed. Count of removed lines shown. |
| `[OK]` | File was scanned but contained no removable rom lines. Not modified. |
| `[WARN]` | A non-fatal issue occurred, e.g. a backup write failed. |
| `[ERROR]` | A file could not be read or written. |

A timestamped log file is automatically written to the `logs/` folder beside the script at the end of each run (see [Logs](#logs)).

---

### Example — Before and After

**Before (original DAT excerpt):**
```xml
<game name="Some.Release-GRP">
    <rom name="Some.Release-GRP.nfo" size="4096" crc="AABBCCDD" />
    <rom name="Some.Release-GRP.sfv" size="512"  crc="11223344" />
    <rom name="Some.Release-GRP.rar" size="104857600" crc="DEADBEEF" />
    <rom name="Some.Release-GRP.r00" size="104857600" crc="CAFEBABE" />
    <rom name="Some.Release-GRP.r01" size="104857600" crc="FEEDFACE" />
    <rom name="Some.Release-GRP.jpg" size="89432"  crc="55667788" />
</game>
```

**After (skeleton DAT):**
```xml
<game name="Some.Release-GRP">
    <rom name="Some.Release-GRP.nfo" size="4096" crc="AABBCCDD" />
    <rom name="Some.Release-GRP.sfv" size="512"  crc="11223344" />
    <rom name="Some.Release-GRP.jpg" size="89432"  crc="55667788" />
</game>
```

The `.rar`, `.r00`, and `.r01` entries are removed. The NFO, SFV, and proof image entries remain.

---

## Tab 2 — Comment Repair

### Purpose

Scene ZIP releases sometimes carry an embedded **archive comment** in their EOCD (End of Central Directory) record. This is a standard ZIP feature, but the presence of a comment — even an empty-looking one — causes the file's binary footprint to differ from what a DAT file expects. Tools like RomVault and ClrMamePro match files by CRC32, size, and sometimes exact byte content; a ZIP with a trailing comment will fail to match a DAT entry that was generated from a clean copy.

The **Comment Repair** tab strips the embedded comment from scene ZIP files and corrects the EOCD comment-length field to zero, restoring the file to a pristine state that matches [dats.site](https://dats.site/home.php) DAT entries exactly.

This repair is used on scene zips to repair them to a pristine state for use with **dats.site datfiles**, located at [https://dats.site/home.php](https://dats.site/home.php).

---

### How It Works

A ZIP file's EOCD record appears near the end of the file and contains a 2-byte comment-length field followed by the comment data itself. The tool:

1. Locates the EOCD signature (`PK\x05\x06`) by scanning from the end of the file.
2. Reads the 2-byte comment-length field at offset +20 within the EOCD.
3. If the comment length is zero, the file is already clean — no write is performed.
4. If a comment is present, a new copy of the file is written that truncates everything after the 22-byte EOCD record and sets the comment-length field to `\x00\x00`.
5. The CRC32 of the fixed output file is computed and optionally logged.

The original file is never modified by default — a new file is written alongside it.

---

### Controls

| Control | Description |
|---|---|
| **Input Mode** | Switch between **Folder (recursive)** — scans all `.zip` files in a folder tree — and **Single file** — processes one ZIP. |
| **Source Folder / Source File** | Folder or file picker. Supports drag-and-drop if `tkinterdnd2` is installed. |
| **Skip files with no comment** | If checked, files that already have no comment are logged as `[CLEAN]` and not written. Avoids unnecessary disk writes. On by default. |
| **Show CRC32 in log** | After fixing a file, logs the CRC32 of the output. Useful for cross-referencing against DAT entries. On by default. |
| **Keep original** | Writes the fixed file as `filename_comment_fixed.zip` beside the original rather than overwriting. Strongly recommended — originals are untouched. On by default. |
| **▶ Run** | Starts processing in a background thread. A progress bar and live ETA are shown. |
| **■ Stop** | Requests a graceful stop at the next file boundary. |
| **Save Log** | Saves the visible log pane to a `.txt` file. |
| **Clear Log** | Clears the log pane display. |

---

### Log Output

| Tag | Meaning |
|---|---|
| `[FIXED]` | Comment was found and stripped. Bytes removed and output filename shown. |
| `[CLEAN]` | No comment present — file skipped (if Skip option is on). |
| `[ERROR]` | File could not be read (not a valid ZIP, permission error, etc.). |
| `CRC32:` | CRC32 of the fixed output file (shown in blue when enabled). |

A running status bar below the options shows current file count, fixed/skipped/error totals, elapsed time, and ETA.

---

### Output Files

By default, fixed files are written as:

```
original_filename_comment_fixed.zip
```

placed in the same directory as the source file. The original is never modified or deleted.

If **Keep original** is unchecked, the fix is applied in-place and no copy is made. Use with caution.

---

## Shared Features

- **Dark theme** — consistent palette across all tabs, optimised for extended use
- **Drag-and-drop** — folder and file pickers accept drag-and-drop when `tkinterdnd2` is installed
- **Threaded processing** — all operations run in background threads; the UI stays responsive during long runs
- **Stop button** — graceful cancellation between files; current file always completes cleanly before stopping
- **Colour-coded log pane** — green for success, cyan for info, amber for warnings, orange/highlighted for errors, blue for CRC values, muted for skipped/clean entries
- **Horizontal scrolling** — log pane scrolls horizontally for long paths

---

## Logs

The **Scene Dat Stripper** automatically saves a timestamped log file to a `logs/` folder created beside `Eggmans_Scene_Tools.py` on every run:

```
logs/scene_dat_stripper_2025-01-15_14-30-00.log
```

Each log includes the run header (folder, backup setting, rules summary), per-file results, and a summary block showing files found, files changed, total lines removed, and elapsed time.

The **Comment Repair** tab does not auto-save a file log — use the **Save Log** button to export the log pane contents if needed.

---

## File Output Reference

| Tool | Input | Output |
|---|---|---|
| Scene Dat Stripper | `release.dat` | Modified in-place (with optional `release.dat.old` backup) |
| Comment Repair (keep original ON) | `release.zip` | `release_comment_fixed.zip` beside original |
| Comment Repair (keep original OFF) | `release.zip` | `release.zip` overwritten in-place |

---

## Known Limitations

- **Scene Dat Stripper** only processes `.dat` and `.xml` files. Other extensions are silently ignored.
- **Scene Dat Stripper** uses line-by-line text processing to preserve exact XML formatting — it does not parse or reformat the XML structure. Malformed XML is handled gracefully (unrecognised lines are kept).
- **Comment Repair** locates the EOCD by scanning from the end of the file using `rfind`. ZIP files with multiple EOCD signatures (e.g. some self-extracting archives) may not be handled correctly.
- **Comment Repair** does not validate the full ZIP structure — it only corrects the comment-length field and truncates trailing comment data. Corrupt ZIPs will be reported as errors.
- Drag-and-drop requires `tkinterdnd2` and may not function in all Python environments. Browse and manual entry always work.

---

## License

This project is released for personal and archival use. No warranty is provided. Use at your own risk.
