# Release Notes

---

## 2026-06-12 — `compress` command shortcut

- `2026-06-12` Added `bin/compress.bat`, a thin launcher that forwards all arguments to `py compress.py`; adding `bin/` to `PATH` lets the tool run as `compress` from any directory
- `2026-06-12` Documented in README: `compress .` runs the tool against the current directory, so courses can be compressed without typing a path

---

## 2026-06-04 — Fix garbled Cyrillic filenames in ffpb output

- `2026-06-04` Pass `PYTHONUTF8=1` in the environment when launching ffpb, forcing its tqdm progress bar to write UTF-8 bytes; without this, the ffpb subprocess inherits the system locale encoding (e.g. CP1251 on Russian Windows) and writes CP1251 bytes that a UTF-8 console misreads as garbled Cyrillic
- `2026-06-04` Also call `SetConsoleOutputCP(65001)` at startup (Windows only, via `ctypes`) so the console is set to UTF-8 even when running from legacy cmd.exe; no-op on Linux/macOS and on modern Windows Terminal (already UTF-8)

---

## 2026-06-02 — Batch directory list from file

- `2026-06-02` New `--list FILE` / `-l FILE` flag accepts a plain-text file where each line is a directory path with an optional profile name (e.g. `D:/Videos/course_78 1080p`); lines starting with `#` and blank lines are ignored
- `2026-06-02` Batch mode shares a single `StopSignal` across all directories — Ctrl+G stops gracefully after the current file, regardless of which directory is being processed
- `2026-06-02` Per-directory progress is persisted via existing `encode.json` mechanism; global batch progress (which dirs are done/failed/pending) is persisted in `<list-file-name>.progress.json` next to the list file
- `2026-06-02` Already-done directories are skipped on resume; failed/pending directories are retried
- `2026-06-02` `--profile` in batch mode sets the default profile; individual list-file entries can override it per-directory
- `2026-06-02` Four integration tests: basic batch encode, comment-line filtering, resume skipping, per-entry profile override
- `2026-06-02` `run_compress` refactored to accept an optional shared `StopSignal` (backward-compatible; single-dir mode unaffected)

---

## 2026-06-02 — Batch list tests expanded

- `2026-06-02` Seven additional integration tests for batch mode: missing list file, all-comment file, `--list` + positional dir conflict, no-args error, global progress schema, new-dir merge on resume, `--profile` flag as default for list entries

---

## 2026-06-02 — Translate all messages to English

- `2026-06-02` All Russian-language user-facing messages in `compress.py` translated to English

---

## 2026-05-28 — Encoding profile config

- `2026-05-28` Added `profiles.toml` (adjacent to `compress.py`) with four built-in profiles: `720p-slow` (default), `1080p`, `480p-fast`, `copy-audio`
- `2026-05-28` New `--profile PROFILE` / `-p PROFILE` CLI flag selects an encoding profile; invalid names auto-print the valid list via `argparse choices=`
- `2026-05-28` All profile names and descriptions listed in `--help` epilog
- `2026-05-28` Removed global `FFPB_ENCODE_ARGS` constant; `_run_ffpb` and `run_compress` now accept `encode_args` parameter
- `2026-05-28` Two new tests: profile flag encodes successfully, invalid profile exits non-zero

---

## 2026-05-28 — Initial release

### Core compression
- `2026-05-28` Batch-compress all videos in a directory using ffpb (libx265, 720p, CRF 30, slow preset)
- `2026-05-28` Non-recursive directory scan; supported inputs: `.mp4 .mkv .avi .mov .webm .m4v`
- `2026-05-28` Output always `.mp4` (required by `movflags +faststart`); written to `<source>/compressed/` by default
- `2026-05-28` `--output` / `-o` flag to specify an explicit output directory
- `2026-05-28` Safe encode: output written to `.tmp.mp4` first, renamed to final name only on success — no corrupt output on crash

### Progress and resume (`encode.json`)
- `2026-05-28` Progress saved to `encode.json` in the output directory after each file
- `2026-05-28` Already-done files skipped on re-run; new files added to the source dir are merged in automatically
- `2026-05-28` Max 3 attempts per file; entries that exceed the limit are marked `failed` and skipped

### Graceful stop
- `2026-05-28` Ctrl+G stops after the current file finishes (Windows); progress fully saved so the next run resumes from the next pending file

### Testing
- `2026-05-28` 9 integration tests covering: basic encode, valid MP4 output, encode.json schema, idempotency, resume, new-file merge, default output dir, error handling
