# -*- coding: utf-8 -*-
"""
Eggman's Scene Tools  v1.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A growing collection of tools for working with scene releases.

Tab 1 – Scene Dat Stripper : Processes scene DAT/XML files and strips
         out RAR volume entries, leaving only support files (NFO, SFV,
         DIZ, proof images, etc.).  The result is a skeleton scene
         record — a lightweight archive of release metadata that tracks
         what was released without requiring the actual data files.
         Ideal for users who follow the scene and want a structured
         release history without the storage overhead of full archives.
         • Folder mode (recursive .dat / .xml scan)
         • Optional .old backup before modifying files
         • Auto-saves timestamped log to logs/ beside the script
         • Colour-coded log with orange error highlighting

Tab 2 – Comment Repair : Strip embedded archive comments from scene
         ZIP releases and fix the EOCD record.
         • Single file or recursive folder mode
         • Writes a fixed copy (filename_comment_fixed.zip)
           beside the original by default — originals untouched
         • CRC32 of output file logged per-file
         • Colour-coded log with orange error highlighting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dependencies (all optional extras):
    pip install tkinterdnd2    # drag-and-drop
"""

import os
import re
import sys
import zlib
import queue
import threading
import tkinter as tk
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from tkinter import ttk, filedialog, scrolledtext
from pathlib import Path

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

# ── Palette ────────────────────────────────────────────────────────────────────

C = {
    "bg":      "#0d0f1a",
    "bg2":     "#161929",
    "bg3":     "#1f2240",
    "bg4":     "#252a4a",
    "accent":  "#7c6ff7",
    "cyan":    "#38bdf8",
    "green":   "#4ade80",
    "amber":   "#fbbf24",
    "red":     "#f87171",
    "orange":  "#fb923c",
    "lblue":   "#7dd3fc",
    "text":    "#dde3f0",
    "muted":   "#5a6382",
    "border":  "#2c3260",
    "err_bg":  "#2a1000",
    "crc_bg":  "#0a1e2a",
}

# ══════════════════════════════════════════════════════════════════════════════
#  CORE — SCENE ZIP (Comment Repair)
# ══════════════════════════════════════════════════════════════════════════════

EOCD_SIG = b"PK\x05\x06"


def crc32_of(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def strip_zip_comment(path: Path, keep_original: bool = True):
    """
    Remove ZIP archive comment and fix EOCD comment-length field.
    If keep_original=True, writes to a new file with '_comment_fixed' appended.
    If keep_original=False, overwrites in-place.
    Returns (ok, crc_after, msg, bytes_removed, out_path)
    """
    try:
        data = path.read_bytes()
    except Exception as e:
        return False, "", f"Read error: {e}", 0, path

    pos = data.rfind(EOCD_SIG)
    if pos == -1:
        return False, "", "EOCD signature not found — not a valid ZIP", 0, path

    if len(data) < pos + 22:
        return False, "", "File too small for a valid EOCD record", 0, path

    comment_len = int.from_bytes(data[pos + 20: pos + 22], "little")

    if comment_len == 0:
        crc = crc32_of(data)
        return True, crc, "No comment present — file unchanged", 0, path

    eocd_end = pos + 22
    new_data  = bytearray(data[:eocd_end])
    new_data[pos + 20: pos + 22] = b"\x00\x00"
    removed = len(data) - len(new_data)

    out_path = path.with_stem(path.stem + "_comment_fixed") if keep_original else path

    try:
        out_path.write_bytes(new_data)
    except Exception as e:
        return False, "", f"Write error: {e}", 0, path

    crc = crc32_of(bytes(new_data))
    return True, crc, f"Comment stripped ({removed} bytes removed)", removed, out_path


# ══════════════════════════════════════════════════════════════════════════════
#  CORE — SCENE DAT STRIPPER
# ══════════════════════════════════════════════════════════════════════════════

# Target only <rom name="..."> lines
_ROM_LINE_PREFIX_RE = re.compile(r'^\s*<rom\s+name="', re.IGNORECASE)
_ROM_NAME_EXTRACT_RE = re.compile(r'^\s*<rom\b[^>]*\bname="([^"]+)"', re.IGNORECASE)

# RAR volume filename patterns:
#   foo.rar  /  foo.part01.rar  /  foo.r00-r99  /  foo.s00-s99  /
#   foo.t00-t99  /  foo.u00-u99  /  foo.v00-v99  /  foo.w00-w99  /
#   foo.001-999
_RAR_FILENAME_RE = re.compile(
    r"""(?ix)
    (?:
        \.part\d{1,6}\.rar
        |
        \.rar
        |
        \.[rstuvw]\d{2}
        |
        \.\d{3}
    )
    $
    """
)


def _is_sfv(name: str) -> bool:
    return name.lower().endswith(".sfv")


def _detect_newline_style(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _read_text_best_effort(path: Path) -> tuple:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            data = path.read_text(encoding=enc, errors="strict")
            return data, enc
        except Exception:
            continue
    data = path.read_text(encoding="utf-8", errors="replace")
    return data, "utf-8 (replace)"


def _should_remove_line(line: str) -> bool:
    if not _ROM_LINE_PREFIX_RE.match(line):
        return False
    m = _ROM_NAME_EXTRACT_RE.match(line)
    if not m:
        return False
    rom_name = m.group(1).strip()
    if not rom_name:
        return False
    if _is_sfv(rom_name):
        return False
    return bool(_RAR_FILENAME_RE.search(rom_name))


def _filter_rar_rom_lines(text: str) -> tuple:
    newline = _detect_newline_style(text)
    lines = text.splitlines()
    kept = []
    removed = 0
    for line in lines:
        if _should_remove_line(line):
            removed += 1
        else:
            kept.append(line)
    new_text = newline.join(kept) + (newline if text.endswith(("\n", "\r\n")) else "")
    return new_text, removed


def _make_old_backup_path(path: Path) -> Path:
    base_old = Path(str(path) + ".old")
    if not base_old.exists():
        return base_old
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(str(path) + f".{stamp}.old")


@dataclass
class _StripperStats:
    files_found: int = 0
    files_changed: int = 0
    total_lines_removed: int = 0
    errors: int = 0


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED WIDGETS
# ══════════════════════════════════════════════════════════════════════════════

class FolderPicker(tk.Frame):
    """Drop zone + entry + browse button."""

    def __init__(self, parent, label="Drop folder here  —  or  Browse →", **kwargs):
        super().__init__(parent, bg=C["bg2"], **kwargs)
        self._var = tk.StringVar()

        self.zone = tk.Label(
            self, text=label,
            bg=C["bg3"], fg=C["muted"],
            font=("Segoe UI", 9), pady=8,
            cursor="hand2", relief="flat"
        )
        self.zone.pack(fill="x", pady=(0, 4))
        self.zone.bind("<Button-1>", lambda e: self._browse())

        row = tk.Frame(self, bg=C["bg2"])
        row.pack(fill="x")

        self.entry = tk.Entry(
            row, textvariable=self._var,
            bg=C["bg3"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", font=("Segoe UI", 9)
        )
        self.entry.pack(side="left", fill="x", expand=True)

        tk.Button(
            row, text="Browse", bg=C["accent"], fg="white",
            relief="flat", font=("Segoe UI", 9, "bold"),
            command=self._browse, cursor="hand2", padx=10
        ).pack(side="right", padx=(6, 0))

        if DND_AVAILABLE:
            self.zone.drop_target_register(DND_FILES)
            self.zone.dnd_bind("<<Drop>>", self._on_drop)
            self.entry.drop_target_register(DND_FILES)
            self.entry.dnd_bind("<<Drop>>", self._on_drop)

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.set(d)

    def _on_drop(self, event):
        self.set(event.data.strip().strip("{}"))

    def set(self, path: str):
        self._var.set(path)
        name = Path(path).name if path else ""
        self.zone.config(
            text=f"📂  {name}" if name else "Drop folder here  —  or  Browse →",
            fg=C["cyan"] if name else C["muted"]
        )

    def get(self) -> str:
        return self._var.get().strip()


class FilePicker(tk.Frame):
    """Single-file drop zone + entry + browse button."""

    def __init__(self, parent, label="Drop .zip file here  —  or  Browse →", **kwargs):
        super().__init__(parent, bg=C["bg2"], **kwargs)
        self._var = tk.StringVar()

        self.zone = tk.Label(
            self, text=label,
            bg=C["bg3"], fg=C["muted"],
            font=("Segoe UI", 9), pady=8,
            cursor="hand2", relief="flat"
        )
        self.zone.pack(fill="x", pady=(0, 4))
        self.zone.bind("<Button-1>", lambda e: self._browse())

        row = tk.Frame(self, bg=C["bg2"])
        row.pack(fill="x")

        self.entry = tk.Entry(
            row, textvariable=self._var,
            bg=C["bg3"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", font=("Segoe UI", 9)
        )
        self.entry.pack(side="left", fill="x", expand=True)

        tk.Button(
            row, text="Browse", bg=C["accent"], fg="white",
            relief="flat", font=("Segoe UI", 9, "bold"),
            command=self._browse, cursor="hand2", padx=10
        ).pack(side="right", padx=(6, 0))

        if DND_AVAILABLE:
            self.zone.drop_target_register(DND_FILES)
            self.zone.dnd_bind("<<Drop>>", self._on_drop)
            self.entry.drop_target_register(DND_FILES)
            self.entry.dnd_bind("<<Drop>>", self._on_drop)

    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        if p:
            self.set(p)

    def _on_drop(self, event):
        self.set(event.data.strip().strip("{}"))

    def set(self, path: str):
        self._var.set(path)
        name = Path(path).name if path else ""
        self.zone.config(
            text=f"📄  {name}" if name else "Drop .zip file here  —  or  Browse →",
            fg=C["cyan"] if name else C["muted"]
        )

    def get(self) -> str:
        return self._var.get().strip()


class LogPane(tk.Frame):
    TAGS = {
        "ok":    C["green"],
        "fail":  C["red"],
        "warn":  C["amber"],
        "info":  C["cyan"],
        "mute":  C["muted"],
        "skip":  C["muted"],
        "error": C["orange"],
        "crc":   C["lblue"],
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=C["bg"], **kwargs)
        self.text = scrolledtext.ScrolledText(
            self, bg=C["bg2"], fg=C["text"],
            font=("Consolas", 9), relief="flat",
            insertbackground=C["text"], state="disabled",
            wrap="none", height=6
        )
        self.text.pack(fill="both", expand=True)

        hbar = tk.Scrollbar(self, orient="horizontal",
                            command=self.text.xview,
                            bg=C["bg3"], troughcolor=C["bg2"],
                            activebackground=C["bg4"])
        hbar.pack(fill="x")
        self.text.config(xscrollcommand=hbar.set)

        for tag, color in self.TAGS.items():
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_configure("error", foreground=C["orange"],
                                background=C["err_bg"],
                                font=("Consolas", 9, "bold"))
        self.text.tag_configure("crc",   foreground=C["lblue"],
                                background=C["crc_bg"])

    def write(self, tag: str, msg: str):
        def _do():
            self.text.config(state="normal")
            self.text.insert("end", msg, tag)
            self.text.see("end")
            self.text.config(state="disabled")
        self.after(0, _do)

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def save(self):
        content = self.text.get("1.0", "end").strip()
        if not content:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="scene_tools_log.txt"
        )
        if p:
            Path(p).write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — SCENE DAT STRIPPER
# ══════════════════════════════════════════════════════════════════════════════

class SceneDatStripperTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["bg"])
        self._stop_flag = threading.Event()
        self._work_queue: queue.Queue = queue.Queue()
        self._worker_thread = None
        self._last_log_path = None
        self._logs_dir = Path(__file__).resolve().parent / "logs"
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._build()
        self.after(100, self._poll_queue)

    def _lf(self, parent, title):
        return tk.LabelFrame(
            parent, text=f"  {title}  ",
            bg=C["bg2"], fg=C["cyan"],
            font=("Segoe UI", 9, "bold"),
            relief="flat", bd=0,
            highlightbackground=C["border"],
            highlightthickness=1,
        )

    def _build(self):
        PAD = dict(padx=10, pady=5)

        # ── Description ───────────────────────────────────────────────────────
        tk.Label(self,
            text=(
                "Processes scene DAT/XML files and strips out RAR volume entries, "
                "leaving only the support files (NFO, SFV, DIZ, proof images, etc.). "
                "The result is a skeleton scene record — a lightweight archive of release metadata "
                "that tracks what was released without requiring the actual data files. "
                "Ideal for users who follow the scene and want a structured release history "
                "without the storage overhead of the full archives. "
                "Scans .dat and .xml files recursively. "
                "An optional .old backup is created before any file is modified. "
                "A timestamped log is auto-saved to a logs/ folder beside this script."
            ),
            bg=C["bg2"], fg=C["muted"], font=("Segoe UI", 8), wraplength=860,
            justify="left", anchor="w", padx=12, pady=6
        ).pack(fill="x", padx=10, pady=(6, 0))

        # ── Folder picker ─────────────────────────────────────────────────────
        ff = self._lf(self, "Source Folder")
        ff.pack(fill="x", **PAD)
        self.folder_picker = FolderPicker(ff)
        self.folder_picker.pack(fill="x", padx=8, pady=6)

        # ── Options ───────────────────────────────────────────────────────────
        of = self._lf(self, "Options")
        of.pack(fill="x", **PAD)

        opt_row = tk.Frame(of, bg=C["bg2"])
        opt_row.pack(fill="x", padx=8, pady=(6, 6))

        self.backup_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_row,
            text="Create .old backup before modifying files  (recommended)",
            variable=self.backup_var,
            bg=C["bg2"], fg=C["green"], selectcolor=C["bg3"],
            activebackground=C["bg2"], font=("Segoe UI", 9, "bold")
        ).pack(side="left")

        # ── Log ───────────────────────────────────────────────────────────────
        self.log = LogPane(self)
        self.log.pack(fill="both", expand=True, padx=10, pady=(2, 4))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn = tk.Frame(self, bg=C["bg"])
        btn.pack(fill="x", padx=10, pady=(0, 10))

        self.start_btn = tk.Button(
            btn, text="▶   Run", bg=C["green"], fg="#000",
            relief="flat", font=("Segoe UI", 10, "bold"),
            command=self._start, cursor="hand2", padx=20
        )
        self.start_btn.pack(side="left")

        self.stop_btn = tk.Button(
            btn, text="■   Stop", bg=C["red"], fg="white",
            relief="flat", font=("Segoe UI", 10, "bold"),
            command=self._request_stop,
            cursor="hand2", padx=20, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(8, 0))

        tk.Button(btn, text="Open Log Folder", bg=C["bg4"], fg=C["muted"],
                  relief="flat", font=("Segoe UI", 9),
                  command=self._open_logs_folder, cursor="hand2", padx=10
                  ).pack(side="left", padx=(8, 0))

        tk.Button(btn, text="Save Log", bg=C["bg4"], fg=C["muted"],
                  relief="flat", font=("Segoe UI", 9),
                  command=self.log.save, cursor="hand2", padx=10
                  ).pack(side="right")
        tk.Button(btn, text="Clear Log", bg=C["bg4"], fg=C["muted"],
                  relief="flat", font=("Segoe UI", 9),
                  command=self.log.clear, cursor="hand2", padx=10
                  ).pack(side="right", padx=(0, 6))

    def _request_stop(self):
        self._stop_flag.set()
        self.log.write("warn", "Stop requested… finishing current file.\n")

    def _open_logs_folder(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(self._logs_dir))
            elif sys.platform == "darwin":
                os.system(f'open "{self._logs_dir}"')
            else:
                os.system(f'xdg-open "{self._logs_dir}"')
        except Exception as e:
            self.log.write("error", f"Failed to open logs folder: {e}\n")

    def _start(self):
        folder = self.folder_picker.get()
        if not folder or not Path(folder).is_dir():
            self.log.write("error", "ERROR: Folder not set or does not exist.\n")
            return
        if self._worker_thread and self._worker_thread.is_alive():
            self.log.write("warn", "A run is already in progress.\n")
            return

        self._stop_flag.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log.clear()

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = self._logs_dir / f"scene_dat_stripper_{timestamp}.log"
        self._last_log_path = log_path

        self._worker_thread = threading.Thread(
            target=self._worker_run,
            args=(Path(folder), log_path, self.backup_var.get()),
            daemon=True,
        )
        self._worker_thread.start()

    def _poll_queue(self):
        try:
            while True:
                item = self._work_queue.get_nowait()
                kind = item.get("kind")
                tag  = item.get("tag", "info")
                msg  = item.get("msg", "")
                if kind in ("log", "done"):
                    self.log.write(tag, msg)
                if kind == "done":
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _q(self, tag: str, msg: str, kind: str = "log"):
        self._work_queue.put({"kind": kind, "tag": tag, "msg": msg})

    def _worker_run(self, folder: Path, log_path: Path, make_backup: bool):
        stats = _StripperStats()
        start = datetime.now()

        def log(tag: str, line: str, log_f=None):
            self._q(tag, line)
            if log_f:
                log_f.write(line)

        try:
            with log_path.open("w", encoding="utf-8", newline="\n") as log_f:
                header = (
                    "Scene DAT Stripper Run\n"
                    f"Started: {start.isoformat(sep=' ', timespec='seconds')}\n"
                    f"Folder:  {folder}\n"
                    f"Backup:  {'ON' if make_backup else 'OFF'} (.old)\n"
                    "Rule:    Removes <rom name=\"...\"> lines whose name ends in a RAR volume pattern\n"
                    "Except:  .sfv entries are ALWAYS preserved\n"
                    "Matches: .rar, .partNN.rar, .r00-.r99, .s00-.s99, .t00-.t99, "
                    ".u00-.u99, .v00-.v99, .w00-.w99, .001-.999\n"
                    "Scans:   .dat, .xml\n"
                    f"{'-' * 60}\n"
                )
                log("info", header, log_f)

                for root_dir, _, files in os.walk(folder):
                    if self._stop_flag.is_set():
                        log("warn", "Stop flag set; exiting scan.\n", log_f)
                        break

                    for name in files:
                        if self._stop_flag.is_set():
                            break
                        if not (name.lower().endswith(".dat") or name.lower().endswith(".xml")):
                            continue

                        path = Path(root_dir) / name
                        stats.files_found += 1

                        try:
                            text, enc = _read_text_best_effort(path)
                            new_text, removed = _filter_rar_rom_lines(text)

                            if removed > 0:
                                if make_backup:
                                    old_path = _make_old_backup_path(path)
                                    try:
                                        old_path.write_text(
                                            text,
                                            encoding=enc if "replace" not in enc else "utf-8",
                                            errors="ignore",
                                        )
                                    except Exception as be:
                                        stats.errors += 1
                                        log("warn", f"[WARN]    Backup failed: {old_path} ({be})\n", log_f)

                                path.write_text(
                                    new_text,
                                    encoding=enc if "replace" not in enc else "utf-8",
                                    errors="ignore",
                                )
                                stats.files_changed += 1
                                stats.total_lines_removed += removed
                                msg = f"[CHANGED] {path.name}  |  removed {removed} rom line(s)\n"
                                log("ok", msg, log_f)
                            else:
                                msg = f"[OK]      {path.name}  |  no removable rom lines found\n"
                                log("skip", msg, log_f)

                        except Exception as e:
                            stats.errors += 1
                            msg = f"[ERROR]   {path.name}  |  {e}\n"
                            log("error", msg, log_f)

                end = datetime.now()
                summary = (
                    f"{'-' * 60}\n"
                    f"Finished: {end.isoformat(sep=' ', timespec='seconds')}\n"
                    f"Elapsed:  {str(end - start)}\n"
                    f"Files found:         {stats.files_found}\n"
                    f"Files changed:       {stats.files_changed}\n"
                    f"Total lines removed: {stats.total_lines_removed}\n"
                    f"Errors/Warns:        {stats.errors}\n"
                )
                log("info", summary, log_f)

            self._q("info", f"Log saved: {log_path}\n", kind="done")

        except Exception as fatal:
            self._q("error", f"Fatal error: {fatal}\n", kind="done")
            try:
                log_path.write_text(f"Fatal error: {fatal}\n", encoding="utf-8")
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — COMMENT REPAIR
# ══════════════════════════════════════════════════════════════════════════════

class SceneZipTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["bg"])
        self._stop = False
        self._build()

    def _lf(self, parent, title):
        return tk.LabelFrame(
            parent, text=f"  {title}  ",
            bg=C["bg2"], fg=C["cyan"],
            font=("Segoe UI", 9, "bold"),
            relief="flat", bd=0,
            highlightbackground=C["border"],
            highlightthickness=1,
        )

    def _build(self):
        PAD = dict(padx=10, pady=5)

        # ── Description ───────────────────────────────────────────────────────
        tk.Label(self,
            text=(
                "Removes embedded archive comments from scene ZIP releases and corrects the EOCD record. "
                "By default a fixed copy is written alongside the original as  filename_comment_fixed.zip  "
                "so the untouched original is always preserved. "
                "Run against a single file or recursively across a folder. CRC32 of each fixed file is logged. "
                "This repair is used on scene zips to repair them to a pristine state for use with "
                "dats.site datfiles, located at https://dats.site/home.php"
            ),
            bg=C["bg2"], fg=C["muted"], font=("Segoe UI", 8), wraplength=860,
            justify="left", anchor="w", padx=12, pady=6
        ).pack(fill="x", padx=10, pady=(6, 0))

        # ── Mode ──────────────────────────────────────────────────────────────
        mf = self._lf(self, "Input Mode")
        mf.pack(fill="x", **PAD)

        mode_row = tk.Frame(mf, bg=C["bg2"])
        mode_row.pack(fill="x", padx=8, pady=(6, 6))

        self.mode_var = tk.StringVar(value="folder")
        tk.Radiobutton(
            mode_row, text="Folder (recursive)", variable=self.mode_var, value="folder",
            bg=C["bg2"], fg=C["text"], selectcolor=C["bg3"],
            activebackground=C["bg2"], font=("Segoe UI", 9),
            command=self._on_mode
        ).pack(side="left")
        tk.Radiobutton(
            mode_row, text="Single file", variable=self.mode_var, value="single",
            bg=C["bg2"], fg=C["text"], selectcolor=C["bg3"],
            activebackground=C["bg2"], font=("Segoe UI", 9),
            command=self._on_mode
        ).pack(side="left", padx=(18, 0))

        # ── Fixed picker container ─────────────────────────────────────────────
        self.picker_container = tk.Frame(self, bg=C["bg"])
        self.picker_container.pack(fill="x")

        self.folder_frame = tk.Frame(self.picker_container, bg=C["bg"])
        ff = self._lf(self.folder_frame, "Source Folder")
        ff.pack(fill="x", padx=10, pady=0)
        self.folder_picker = FolderPicker(ff)
        self.folder_picker.pack(fill="x", padx=8, pady=6)

        self.file_frame = tk.Frame(self.picker_container, bg=C["bg"])
        sf = self._lf(self.file_frame, "Source File")
        sf.pack(fill="x", padx=10, pady=0)
        self.file_picker = FilePicker(sf)
        self.file_picker.pack(fill="x", padx=8, pady=6)

        self._on_mode()

        # ── Options ───────────────────────────────────────────────────────────
        of = self._lf(self, "Options")
        of.pack(fill="x", **PAD)

        opt_row = tk.Frame(of, bg=C["bg2"])
        opt_row.pack(fill="x", padx=8, pady=(6, 2))

        self.skip_clean_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_row, text="Skip files with no comment (no write)",
            variable=self.skip_clean_var,
            bg=C["bg2"], fg=C["text"], selectcolor=C["bg3"],
            activebackground=C["bg2"], font=("Segoe UI", 9)
        ).pack(side="left")

        self.show_crc_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_row, text="Show CRC32 in log",
            variable=self.show_crc_var,
            bg=C["bg2"], fg=C["text"], selectcolor=C["bg3"],
            activebackground=C["bg2"], font=("Segoe UI", 9)
        ).pack(side="left", padx=(24, 0))

        opt_row2 = tk.Frame(of, bg=C["bg2"])
        opt_row2.pack(fill="x", padx=8, pady=(0, 6))

        self.keep_original_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_row2,
            text="Keep original — write fixed copy as  filename_comment_fixed.zip  (recommended)",
            variable=self.keep_original_var,
            bg=C["bg2"], fg=C["green"], selectcolor=C["bg3"],
            activebackground=C["bg2"], font=("Segoe UI", 9, "bold")
        ).pack(side="left")

        # ── Stats + Progress ──────────────────────────────────────────────────
        stat_row = tk.Frame(self, bg=C["bg"])
        stat_row.pack(fill="x", padx=10, pady=(6, 1))
        self.stat_var = tk.StringVar(value="Ready.")
        tk.Label(stat_row, textvariable=self.stat_var,
                 bg=C["bg"], fg=C["muted"],
                 font=("Segoe UI", 8)).pack(side="left")

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=10, pady=(1, 4))

        # ── Log ───────────────────────────────────────────────────────────────
        self.log = LogPane(self)
        self.log.pack(fill="both", expand=True, padx=10, pady=(2, 4))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn = tk.Frame(self, bg=C["bg"])
        btn.pack(fill="x", padx=10, pady=(0, 10))

        self.start_btn = tk.Button(
            btn, text="▶   Run", bg=C["green"], fg="#000",
            relief="flat", font=("Segoe UI", 10, "bold"),
            command=self._start, cursor="hand2", padx=20
        )
        self.start_btn.pack(side="left")

        self.stop_btn = tk.Button(
            btn, text="■   Stop", bg=C["red"], fg="white",
            relief="flat", font=("Segoe UI", 10, "bold"),
            command=lambda: setattr(self, "_stop", True),
            cursor="hand2", padx=20, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(8, 0))

        tk.Button(btn, text="Save Log", bg=C["bg4"], fg=C["muted"],
                  relief="flat", font=("Segoe UI", 9),
                  command=self.log.save, cursor="hand2", padx=10
                  ).pack(side="right")
        tk.Button(btn, text="Clear Log", bg=C["bg4"], fg=C["muted"],
                  relief="flat", font=("Segoe UI", 9),
                  command=self.log.clear, cursor="hand2", padx=10
                  ).pack(side="right", padx=(0, 6))

    def _on_mode(self):
        if self.mode_var.get() == "folder":
            self.file_frame.pack_forget()
            self.folder_frame.pack(fill="x")
        else:
            self.folder_frame.pack_forget()
            self.file_frame.pack(fill="x")

    def _stat(self, msg):
        self.after(0, lambda: self.stat_var.set(msg))

    def _prog(self, val):
        self.after(0, lambda: self.progress.config(value=val))

    def _start(self):
        mode = self.mode_var.get()
        if mode == "folder":
            src = self.folder_picker.get()
            if not src or not Path(src).is_dir():
                self.log.write("error", "ERROR: Folder not set or does not exist.\n")
                return
            targets = sorted(Path(src).rglob("*.zip"))
        else:
            src = self.file_picker.get()
            if not src or not Path(src).is_file():
                self.log.write("error", "ERROR: File not set or does not exist.\n")
                return
            targets = [Path(src)]

        if not targets:
            self.log.write("info", "No .zip files found.\n")
            return

        self._stop = False
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        threading.Thread(
            target=self._run,
            args=(targets, self.skip_clean_var.get(),
                  self.show_crc_var.get(), self.keep_original_var.get()),
            daemon=True
        ).start()

    def _run(self, targets: list, skip_clean: bool, show_crc: bool, keep_original: bool):
        t0    = time.time()
        total = len(targets)
        ok = skipped = errors = total_removed = 0

        mode_note = "copy mode (originals kept)" if keep_original else "in-place mode (originals overwritten)"
        self.log.write("info", f"Processing {total} ZIP file(s)  [{mode_note}]…\n")
        self.log.write("info", "─" * 64 + "\n")

        for i, path in enumerate(targets, 1):
            if self._stop:
                self.log.write("warn", f"[STOPPED at {i-1}/{total}]\n")
                break

            elapsed = time.time() - t0
            rate    = i / elapsed if elapsed > 0 else 0
            eta     = (total - i) / rate if rate > 0 else 0
            self._stat(
                f"{i}/{total}  │  ✓ {ok}  ↷ {skipped}  ✗ {errors}  │  "
                f"{timedelta(seconds=int(elapsed))} elapsed  ETA {timedelta(seconds=int(eta))}"
            )
            self._prog(100 * i / total)

            success, crc, msg, removed, out_path = strip_zip_comment(path, keep_original)

            if not success:
                self.log.write("error",
                    f"[ERROR]  {path.name}\n"
                    f"         {msg}\n")
                errors += 1
                continue

            if removed == 0 and skip_clean:
                self.log.write("skip", f"[CLEAN]  {path.name}  — no comment\n")
                skipped += 1
                continue

            tag  = "ok" if removed > 0 else "skip"
            verb = "[FIXED]" if removed > 0 else "[CLEAN]"
            dest_note = f"  →  {out_path.name}" if keep_original and removed > 0 else ""
            self.log.write(tag, f"{verb}  {path.name}{dest_note}  — {msg}\n")

            if show_crc and crc:
                self.log.write("crc", f"         CRC32: {crc}\n")

            if removed > 0:
                ok += 1
                total_removed += removed

        elapsed = time.time() - t0
        self.log.write("info", "─" * 64 + "\n")
        self.log.write("info",
            f"Done.  Fixed: {ok}  Clean/skipped: {skipped}  Errors: {errors}  │  "
            f"Total bytes removed: {total_removed:,}  │  "
            f"{timedelta(seconds=int(elapsed))}\n"
        )
        self._stat(
            f"Done — Fixed: {ok}, Skipped: {skipped}, Errors: {errors}, "
            f"Bytes removed: {total_removed:,}"
        )
        self._prog(100)
        self._finish()

    def _finish(self):
        self.after(0, lambda: self.start_btn.config(state="normal"))
        self.after(0, lambda: self.stop_btn.config(state="disabled"))


# ══════════════════════════════════════════════════════════════════════════════
#  APPLICATION SHELL
# ══════════════════════════════════════════════════════════════════════════════

class App:
    def __init__(self):
        Root = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk
        self.root = Root()
        self.root.title("Eggman's Scene Tools  v1.1")
        self.root.geometry("900x800")
        self.root.minsize(900, 600)
        self.root.configure(bg=C["bg"])

        self._apply_style()
        self._build_header()
        self._build_notebook()

    def _apply_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TNotebook",     background=C["bg"],  borderwidth=0)
        s.configure("TNotebook.Tab", background=C["bg3"], foreground=C["muted"],
                    font=("Segoe UI", 10, "bold"), padding=[18, 7])
        s.map("TNotebook.Tab",
              background=[("selected", C["bg2"])],
              foreground=[("selected", C["cyan"])])
        s.configure("Horizontal.TProgressbar",
                    troughcolor=C["bg3"], background=C["accent"],
                    borderwidth=0, thickness=5)

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=C["bg2"], pady=9)
        hdr.pack(fill="x")

        tk.Label(hdr, text="🎬  Eggman's Scene Tools",
                 bg=C["bg2"], fg=C["cyan"],
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16)
        tk.Label(hdr, text="v1.1",
                 bg=C["bg2"], fg=C["muted"],
                 font=("Segoe UI", 9)).pack(side="left", pady=2)

        if not DND_AVAILABLE:
            tk.Label(hdr, text="⚠  pip install tkinterdnd2  (drag-and-drop)",
                     bg=C["bg2"], fg=C["amber"],
                     font=("Segoe UI", 8)).pack(side="right", padx=16)

    def _build_notebook(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True)
        nb.add(SceneDatStripperTab(nb), text="  🗂  Scene Dat Stripper  ")
        nb.add(SceneZipTab(nb),         text="  🗜  Comment Repair  ")

    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════════════════

def main():
    App().run()


if __name__ == "__main__":
    main()
