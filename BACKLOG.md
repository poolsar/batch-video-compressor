# Backlog

Planned features and technical tasks not yet implemented.
Move completed items to `RELEASE_NOTES.md` with a timestamp.

---

## Batch directory list from file

`py compress.py --list courses.txt` accepts a plain-text file where each line is a directory
path with an optional profile name, e.g.:

```
D:/Videos/course_78
D:/Videos/course_79 1080p
D:/Videos/course_80 480p-fast
```

Behaviour mirrors single-directory mode: Ctrl+G stops gracefully after the current file,
progress is persisted per output directory (existing `encode.json` files are reused), and
already-completed directories are skipped on resume. Lines starting with `#` are ignored.

