# batch-video-compressor

Batch-compress a directory of videos to H.265/720p using [ffpb](https://github.com/althonos/ffpb).
Supports graceful interrupt (Ctrl+G) and resumes automatically from where it left off.

## Requirements

- Python 3.9+
- [ffpb](https://github.com/althonos/ffpb) — `pip install ffpb`
- [ffmpeg](https://ffmpeg.org/) — must be on PATH

## Usage

```bash
# compress all videos in a directory (output → <dir>/compressed/)
py compress.py D:/Videos/course_78

# explicit output directory
py compress.py D:/Videos/course_78 --output D:/Videos/course_78_x265
```

Supported input formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`.
Output is always `.mp4` (H.265, 720p).

## Encode settings

```
-c:v libx265  -vf scale=-2:720  -crf 30  -preset slow  -movflags +faststart
```

Edit `FFPB_ENCODE_ARGS` in `compress.py` to change codec, resolution, or quality.

## Resume and progress

Progress is saved to `encode.json` in the output directory after each file.
Re-running the same command skips already-done files and picks up from where it stopped.
Files that fail 3 times are marked `failed` and skipped on subsequent runs.

To retry a failed file, reset its `status` to `"pending"` and `attempts` to `0` in `encode.json`.

## Graceful stop

Press **Ctrl+G** to stop after the current file finishes. Progress is fully saved — the next
run continues from the next pending file.

## Development

```bash
uv sync          # install dev dependencies
make test        # run integration tests (requires ffpb on PATH)
make check       # lint + test
```
