# Release Notes

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
