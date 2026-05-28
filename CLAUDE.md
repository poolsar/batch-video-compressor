# batch-video-compressor — Claude Code context

## Maintenance instructions for Claude

- After implementing any feature or fix, append an entry to `RELEASE_NOTES.md`.
- If an improvement idea surfaces during implementation but is out of scope for the current
  feature, suggest adding it to `BACKLOG.md` and ask the user before doing so.
- If a feature being implemented is already listed in `BACKLOG.md`, remove it from there
  and ensure `RELEASE_NOTES.md` has an entry for it (add one if missing).

## What this project is

A single-file Python CLI (`compress.py`) that batch-compresses video files using
**ffpb** (an ffmpeg wrapper with a progress bar). Encodes to H.265/720p with resume
support via a per-run `encode.json` progress file.

## File layout

```
compress.py          — CLI entry point and all logic (single file)
data/
  video-sample.mp4   — fixture for integration tests
tests/
  conftest.py        — adds repo root to sys.path
  test_compress.py   — 9 integration tests (offline, require ffpb on PATH)
pyproject.toml       — project metadata and ruff config
Makefile             — shortcuts: install / test / lint / format / check
```

## Running the tool

```bash
# compress all videos in a directory (output → <dir>/compressed/)
py compress.py D:/Videos/course_78

# explicit output directory
py compress.py D:/Videos/course_78 --output D:/Videos/course_78_x265

# press Ctrl+G to stop gracefully after the current file finishes
```

## Encode settings

`ffpb -i <input> -c:v libx265 -vf scale=-2:720 -crf 30 -preset slow -movflags +faststart <output>`

Constant `FFPB_ENCODE_ARGS` in `compress.py` — change it to adjust codec, resolution, or quality.

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
  always finishes cleanly.
- **Video discovery**: non-recursive `os.scandir` on the source directory. Extensions:
  `.mp4 .mkv .avi .mov .webm .m4v`. Sorted alphabetically — numeric prefixes (e.g. `1. Video.mp4`)
  preserve natural order.
- **Output always `.mp4`**: regardless of input container, output is `.mp4` (required by
  `movflags +faststart`).
- **`sys.stdout/stderr.reconfigure(encoding="utf-8")`**: called at module level so Cyrillic
  messages render correctly on Windows regardless of system locale.

## Progress file schema (`encode.json`)

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

## Dependencies

- **ffpb** — must be on PATH (`pip install ffpb`); wraps ffmpeg with a progress bar
- **ffmpeg** — must be on PATH; used by ffpb to perform the actual encode
- No Python package dependencies beyond the stdlib

## Testing

```bash
uv run pytest tests/ -v   # or: make test
```

Tests are offline (no network). All 9 tests are skipped automatically if `ffpb` is not on PATH.
Each test that encodes uses `data/video-sample.mp4` (~3.5 MB); full suite takes ~2 minutes.
