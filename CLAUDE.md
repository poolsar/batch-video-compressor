# batch-video-compressor — Claude Code context

## Maintenance instructions for Claude

- After implementing any feature or fix, append an entry to `RELEASE_NOTES.md`.
- If an improvement idea surfaces during implementation but is out of scope for the current
  feature, suggest adding it to `BACKLOG.md` and ask the user before doing so.
- If a feature being implemented is already listed in `BACKLOG.md`, remove it from there
  and ensure `RELEASE_NOTES.md` has an entry for it (add one if missing).
- After each commit, review `CLAUDE.md` and `README.md` and update any sections that are
  now stale or incomplete (file layout, usage examples, encode settings, dependencies, etc.).
  Only update what has actually changed; leave accurate sections alone.
- **CRITICAL — stale docs cause code degradation.** Whenever a discrepancy is detected
  between any `.md` file and the actual code — wrong function names, removed constants,
  outdated flags, incorrect file paths, wrong dependency versions, wrong test counts, etc. —
  STOP and fix the `.md` file immediately, before continuing with any other work. Do not
  silently read past misleading content. Do not act on it. Correct it first.
- **DOUBLE CRITICAL — `CLAUDE.md` is the highest-risk file.** This file is loaded as
  primary context at the start of every session. A single stale fact here poisons every
  decision that follows and is the most direct path to code degradation. Treat any
  inaccuracy in `CLAUDE.md` as a blocking issue: verify against the actual code, update
  `CLAUDE.md` to match the code (never the other way around), and never proceed with
  work while knowing it contains incorrect information.

## What this project is

A single-file Python CLI (`compress.py`) that batch-compresses video files using
**ffpb** (an ffmpeg wrapper with a progress bar). Encodes to H.265/720p with resume
support via a per-run `encode.json` progress file.

## File layout

```
compress.py          — CLI entry point and all logic (single file)
profiles.toml        — named encoding presets (loaded at startup)
data/
  video-sample.mp4   — fixture for integration tests
tests/
  conftest.py        — adds repo root to sys.path
  test_compress.py   — 22 integration tests (offline, require ffpb on PATH)
pyproject.toml       — project metadata and ruff config
Makefile             — shortcuts: install / test / lint / format / check
```

## Running the tool

```bash
# compress all videos in a directory (output → <dir>/compressed/)
py compress.py D:/Videos/course_78

# explicit output directory
py compress.py D:/Videos/course_78 --output D:/Videos/course_78_x265

# use a non-default encoding profile
py compress.py D:/Videos/course_78 --profile 1080p

# batch mode: compress multiple directories listed in a file
py compress.py --list courses.txt

# press Ctrl+G to stop gracefully after the current file finishes
```

List file format (`courses.txt`): one directory per line, optional profile name after the path.
Lines starting with `#` and blank lines are ignored.

```
D:/Videos/course_78
D:/Videos/course_79 1080p
# this line is a comment
D:/Videos/course_80 480p-fast
```

## Encode settings

Profiles are defined in `profiles.toml` (adjacent to `compress.py`). Each profile has a
`description` and an `args` list passed verbatim to ffpb. The `default` key sets which
profile is used when `--profile` is omitted.

Built-in profiles: `720p-slow` (default), `1080p`, `480p-fast`, `copy-audio`.
To add or adjust a profile, edit `profiles.toml` — no changes to `compress.py` needed.

## Key implementation decisions

- **Safe encode**: output is written to `<file>.tmp.mp4` first, renamed to final name only on
  success. A mid-encode crash leaves no corrupt output.
- **Progress file (`encode.json`)**: stored in the output directory. Tracks `input`, `output`,
  `status` (`pending` | `done` | `failed`), `attempts`, `last_error`. Files already `done` are
  skipped on re-run; new files added to the source dir are merged in automatically.
  Max attempts: 3 — after that the entry is marked `failed` and skipped.
- **Ctrl+G graceful stop**: `StopSignal` class runs a daemon thread that polls `msvcrt.kbhit()`
  (Windows-only; silently disabled on Linux/macOS). Sets `stop.requested` when BEL byte (`\x07`)
  is detected. The loop checks the flag *before* starting each new file, so the current encode
  always finishes cleanly. In batch mode a single `StopSignal` is shared across all directories
  (passed into `run_compress` via its optional `stop` parameter).
- **Video discovery**: non-recursive `os.scandir` on the source directory. Extensions:
  `.mp4 .mkv .avi .mov .webm .m4v`. Sorted alphabetically — numeric prefixes (e.g. `1. Video.mp4`)
  preserve natural order.
- **Output always `.mp4`**: regardless of input container, output is `.mp4` (required by
  `movflags +faststart`).
- **`sys.stdout/stderr.reconfigure(encoding="utf-8")`**: called at module level so Cyrillic
  messages render correctly on Windows regardless of system locale.
- **Batch list mode (`--list`)**: `run_batch` parses the list file, creates/merges a global
  progress file (`<list-file-name>.progress.json` next to the list file), then calls `run_compress`
  per directory. Already-done directories are skipped on resume; failed/pending are retried.
  Each directory still gets its own `encode.json` in its output directory.

## Progress file schemas

### Per-directory (`encode.json`)

```json
{
  "source_dir": "D:/Videos/course_78",
  "output_dir":  "D:/Videos/course_78/compressed",
  "created_at":  "2026-05-28T10:00:00",
  "files": [
    {
      "input":      "D:/Videos/course_78/1. Video.mp4",
      "output":     "D:/Videos/course_78/compressed/1. Video.mp4",
      "status":     "done",
      "attempts":   1,
      "last_error": null
    }
  ]
}
```

### Global batch progress (`<list-file>.progress.json`)

```json
{
  "list_file":  "/abs/path/courses.txt",
  "created_at": "2026-06-02T10:00:00",
  "directories": [
    {
      "source_dir": "D:/Videos/course_78",
      "output_dir": "D:/Videos/course_78/compressed",
      "profile":    "720p-slow",
      "status":     "done",
      "last_error": null
    }
  ]
}
```

## Dependencies

- **ffpb** — must be on PATH (`pip install ffpb`); wraps ffmpeg with a progress bar
- **ffmpeg** — must be on PATH; used by ffpb to perform the actual encode
- No Python package dependencies beyond the stdlib

## Testing

```bash
uv run pytest tests/ -v   # or: make test
```

Tests are offline (no network). All 22 tests are skipped automatically if `ffpb` is not on PATH.
Each test that encodes uses `data/video-sample.mp4` (~3.5 MB); full suite takes ~4 minutes.
