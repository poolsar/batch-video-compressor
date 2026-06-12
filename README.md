# batch-video-compressor

Batch-compress a directory of videos to H.265/720p using [ffpb](https://github.com/althonos/ffpb).
Supports graceful interrupt (Ctrl+G) and resumes automatically from where it left off.

## Requirements

- Python 3.11+
- [ffpb](https://github.com/althonos/ffpb) — `pip install ffpb`
- [ffmpeg](https://ffmpeg.org/) — must be on PATH

## Usage

```bash
# compress all videos in a directory (output → <dir>/compressed/)
py compress.py D:/Videos/course_78

# explicit output directory
py compress.py D:/Videos/course_78 --output D:/Videos/course_78_x265

# use a non-default encoding profile
py compress.py D:/Videos/course_78 --profile 1080p

# batch mode: compress multiple directories from a list file
py compress.py --list courses.txt
```

Supported input formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`.
Output is always `.mp4`.

## Shortcut: run as `compress` from anywhere

`bin/compress.bat` forwards all arguments to `py compress.py`. Add the `bin/` directory
to your `PATH` (Windows: *System Properties → Environment Variables → Path*) to run the
tool as `compress` from any directory — no need to type the path to `compress.py`.

```bash
# from anywhere on the machine
compress D:/Videos/course_78 --profile 1080p

# or cd into the course directory and compress it in place
cd D:/Videos/course_78
compress .
```

Every flag (`--output`, `--profile`, `--list`, etc.) works the same as with `py compress.py`.

## Batch mode

`--list FILE` (`-l FILE`) accepts a plain-text file where each line is a directory path
with an optional profile name. Lines starting with `#` and blank lines are ignored.

```
D:/Videos/course_78
D:/Videos/course_79 1080p
# this line is a comment
D:/Videos/course_80 480p-fast
```

Each directory uses its own `encode.json` for per-file progress. Global batch progress
(which directories are done/pending/failed) is saved to `<list-file>.progress.json` next
to the list file. Already-done directories are skipped on resume.

`--profile NAME` sets the default profile for entries that don't specify one.

## Encoding profiles

Profiles are defined in `profiles.toml`. Pass `--profile NAME` (or `-p NAME`) to select one;
omit it to use the default. An invalid name prints the list of valid choices automatically.

| Profile | Description |
|---|---|
| `720p-slow` | H.265 720p, CRF 30, slow preset *(default)* |
| `1080p` | H.265 1080p, CRF 28, slow preset |
| `480p-fast` | H.265 480p, CRF 32, fast preset |
| `copy-audio` | H.265 720p, CRF 30, slow preset, original audio stream copied |

To add or adjust a profile, edit `profiles.toml` — no changes to `compress.py` needed.

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
