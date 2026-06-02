"""
Integration tests for compress.py.

Offline — no network required. Requires ffpb on PATH; all tests are
skipped automatically if ffpb is missing.

Uses data/video-sample.mp4 as real input.

Run:
    uv run pytest tests/ -v
    make test
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "compress.py")
SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "video-sample.mp4")

pytestmark = pytest.mark.skipif(
    shutil.which("ffpb") is None,
    reason="ffpb not found on PATH",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _read_encode_json(output_dir: str) -> dict:
    with open(os.path.join(output_dir, "encode.json"), encoding="utf-8") as f:
        return json.load(f)


def _write_encode_json(output_dir: str, progress: dict) -> None:
    with open(os.path.join(output_dir, "encode.json"), "w", encoding="utf-8") as f:
        json.dump(progress, f)


def _make_source(tmp_path, *names: str) -> tuple[str, str]:
    """Create a source dir populated with copies of SAMPLE. Returns (source_dir, output_dir)."""
    source = tmp_path / "source"
    source.mkdir()
    for name in names:
        shutil.copy2(SAMPLE, source / name)
    output = str(tmp_path / "compressed")
    return str(source), output


# ---------------------------------------------------------------------------
# Basic compression
# ---------------------------------------------------------------------------


def test_compress_creates_output_file(tmp_path):
    source_dir, output_dir = _make_source(tmp_path, "video-sample.mp4")
    r = _run([source_dir, "--output", output_dir])

    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"

    mp4s = [f for f in os.listdir(output_dir) if f.endswith(".mp4")]
    assert len(mp4s) == 1
    assert os.path.getsize(os.path.join(output_dir, mp4s[0])) > 0


def test_compress_output_is_valid_mp4(tmp_path):
    """Output must be a valid MP4 — verified by the 'ftyp' box at byte offset 4."""
    source_dir, output_dir = _make_source(tmp_path, "video-sample.mp4")
    _run([source_dir, "--output", output_dir])

    entry = _read_encode_json(output_dir)["files"][0]
    assert entry["output"].endswith(".mp4")
    with open(entry["output"], "rb") as f:
        f.seek(4)
        assert f.read(4) == b"ftyp", "Output is not a valid MP4 container"


# ---------------------------------------------------------------------------
# encode.json schema
# ---------------------------------------------------------------------------


def test_compress_encode_json_schema(tmp_path):
    """encode.json must contain all required top-level keys and per-file fields."""
    source_dir, output_dir = _make_source(tmp_path, "video-sample.mp4")
    _run([source_dir, "--output", output_dir])

    prog = _read_encode_json(output_dir)
    for key in ("source_dir", "output_dir", "created_at", "files"):
        assert key in prog, f"Top-level key missing: {key}"

    assert len(prog["files"]) == 1
    entry = prog["files"][0]
    for field in ("input", "output", "status", "attempts", "last_error"):
        assert field in entry, f"Per-file field missing: {field}"

    assert entry["status"] == "done"
    assert entry["attempts"] == 1
    assert entry["last_error"] is None
    assert os.path.isfile(entry["output"])


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_compress_idempotency(tmp_path):
    """Second run must skip done files without re-encoding (attempts stays the same)."""
    source_dir, output_dir = _make_source(tmp_path, "video-sample.mp4")

    r1 = _run([source_dir, "--output", output_dir])
    assert r1.returncode == 0, r1.stdout

    prog1 = _read_encode_json(output_dir)
    attempts_after_first = prog1["files"][0]["attempts"]
    mtime = os.path.getmtime(prog1["files"][0]["output"])

    r2 = _run([source_dir, "--output", output_dir])
    assert r2.returncode == 0
    assert "Skipped" in r2.stdout, "Expected skip notice on second run"

    prog2 = _read_encode_json(output_dir)
    assert prog2["files"][0]["attempts"] == attempts_after_first  # not incremented
    assert os.path.getmtime(prog2["files"][0]["output"]) == mtime  # output not rewritten


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_compress_resumes_pending(tmp_path):
    """Resetting status to 'pending' in encode.json causes the file to be re-encoded."""
    source_dir, output_dir = _make_source(tmp_path, "video-sample.mp4")

    r1 = _run([source_dir, "--output", output_dir])
    assert r1.returncode == 0

    prog = _read_encode_json(output_dir)
    prog["files"][0]["status"] = "pending"
    prog["files"][0]["attempts"] = 0
    _write_encode_json(output_dir, prog)

    r2 = _run([source_dir, "--output", output_dir])
    assert r2.returncode == 0

    prog2 = _read_encode_json(output_dir)
    assert prog2["files"][0]["status"] == "done"
    assert prog2["files"][0]["attempts"] == 1


def test_compress_merges_new_files(tmp_path):
    """A video added to the source dir after the first run is picked up on the next run."""
    source_dir, output_dir = _make_source(tmp_path, "first.mp4")

    r1 = _run([source_dir, "--output", output_dir])
    assert r1.returncode == 0
    assert len(_read_encode_json(output_dir)["files"]) == 1

    shutil.copy2(SAMPLE, os.path.join(source_dir, "second.mp4"))

    r2 = _run([source_dir, "--output", output_dir])
    assert r2.returncode == 0

    prog = _read_encode_json(output_dir)
    assert len(prog["files"]) == 2
    assert all(e["status"] == "done" for e in prog["files"])


# ---------------------------------------------------------------------------
# Default output directory
# ---------------------------------------------------------------------------


def test_compress_default_output_dir(tmp_path):
    """Without --output the compressed files land in <source_dir>/compressed/."""
    source_dir = str(tmp_path / "source")
    os.makedirs(source_dir)
    shutil.copy2(SAMPLE, os.path.join(source_dir, "video-sample.mp4"))

    r = _run([source_dir])
    assert r.returncode == 0

    default_output = os.path.join(source_dir, "compressed")
    assert os.path.isdir(default_output), "compressed/ subdir not created"
    assert os.path.isfile(os.path.join(default_output, "encode.json"))
    mp4s = [f for f in os.listdir(default_output) if f.endswith(".mp4")]
    assert len(mp4s) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_compress_missing_source_dir_exits_nonzero():
    r = _run(["/nonexistent/path/does/not/exist"])
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_compress_empty_dir_exits_zero(tmp_path):
    """A directory with no video files exits cleanly (zero) with an informational message."""
    source_dir = str(tmp_path / "empty")
    os.makedirs(source_dir)

    r = _run([source_dir])
    assert r.returncode == 0
    assert "no video" in r.stdout.lower()


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------


def test_compress_profile_flag(tmp_path):
    """--profile 480p-fast must encode successfully and produce a valid MP4."""
    source_dir, output_dir = _make_source(tmp_path, "video-sample.mp4")
    r = _run([source_dir, "--output", output_dir, "--profile", "480p-fast"])

    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    mp4s = [f for f in os.listdir(output_dir) if f.endswith(".mp4")]
    assert len(mp4s) == 1
    assert os.path.getsize(os.path.join(output_dir, mp4s[0])) > 0


def test_compress_invalid_profile_exits_nonzero(tmp_path):
    """An unrecognised --profile value must cause a non-zero exit with a helpful message."""
    source_dir = str(tmp_path / "source")
    os.makedirs(source_dir)

    r = _run([source_dir, "--profile", "nonexistent-profile"])
    assert r.returncode != 0
    assert "nonexistent-profile" in r.stderr


# ---------------------------------------------------------------------------
# Batch list mode (--list)
# ---------------------------------------------------------------------------


def test_batch_list_basic(tmp_path):
    """--list compresses all directories in the list file and writes a global progress file."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    d2 = tmp_path / "course2"
    d2.mkdir()
    shutil.copy2(SAMPLE, d2 / "video.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(f"{d1}\n{d2}\n", encoding="utf-8")

    r = _run(["--list", str(list_file)])
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"

    for d in (d1, d2):
        out = d / "compressed"
        assert os.path.isfile(out / "encode.json"), f"encode.json missing in {out}"
        mp4s = [f for f in os.listdir(out) if f.endswith(".mp4")]
        assert len(mp4s) == 1

    progress_file = tmp_path / "courses.progress.json"
    assert progress_file.exists(), "global progress file not created"
    with open(progress_file, encoding="utf-8") as f:
        prog = json.load(f)
    assert len(prog["directories"]) == 2
    assert all(d["status"] == "done" for d in prog["directories"])


def test_batch_list_comment_lines(tmp_path):
    """Lines starting with '#' and blank lines in the list file are ignored."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(
        f"# this is a comment\n\n{d1}\n# another comment\n",
        encoding="utf-8",
    )

    r = _run(["--list", str(list_file)])
    assert r.returncode == 0

    with open(tmp_path / "courses.progress.json", encoding="utf-8") as f:
        prog = json.load(f)
    assert len(prog["directories"]) == 1
    assert prog["directories"][0]["status"] == "done"


def test_batch_list_resume(tmp_path):
    """Re-running with --list skips already-done directories."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    d2 = tmp_path / "course2"
    d2.mkdir()
    shutil.copy2(SAMPLE, d2 / "video.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(f"{d1}\n{d2}\n", encoding="utf-8")

    r1 = _run(["--list", str(list_file)])
    assert r1.returncode == 0

    r2 = _run(["--list", str(list_file)])
    assert r2.returncode == 0
    assert r2.stdout.count("Skipped (already done)") == 2


def test_batch_list_per_entry_profile(tmp_path):
    """A profile name after the directory path in the list file overrides the default."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(f"{d1} 480p-fast\n", encoding="utf-8")

    r = _run(["--list", str(list_file)])
    assert r.returncode == 0

    with open(tmp_path / "courses.progress.json", encoding="utf-8") as f:
        prog = json.load(f)
    assert prog["directories"][0]["profile"] == "480p-fast"
    assert prog["directories"][0]["status"] == "done"


def test_batch_list_missing_file(tmp_path):
    """--list with a non-existent file exits non-zero with an error message."""
    r = _run(["--list", str(tmp_path / "nonexistent.txt")])
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_batch_list_empty_file(tmp_path):
    """A list file containing only comments and blank lines exits zero with an informational message."""
    list_file = tmp_path / "courses.txt"
    list_file.write_text("# comment\n\n# another comment\n", encoding="utf-8")

    r = _run(["--list", str(list_file)])
    assert r.returncode == 0
    assert "no directories" in r.stdout.lower()


def test_batch_list_and_dir_mutually_exclusive(tmp_path):
    """Passing both a positional directory and --list must exit non-zero."""
    source_dir = str(tmp_path / "source")
    os.makedirs(source_dir)
    list_file = tmp_path / "courses.txt"
    list_file.write_text(source_dir, encoding="utf-8")

    r = _run([source_dir, "--list", str(list_file)])
    assert r.returncode != 0


def test_batch_no_args_exits_nonzero():
    """Running with no arguments (no dir, no --list) must exit non-zero."""
    r = _run([])
    assert r.returncode != 0


def test_batch_list_progress_schema(tmp_path):
    """Global progress file must contain all required top-level keys and per-directory fields."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(f"{d1}\n", encoding="utf-8")

    r = _run(["--list", str(list_file)])
    assert r.returncode == 0

    progress_file = tmp_path / "courses.progress.json"
    assert progress_file.exists()
    with open(progress_file, encoding="utf-8") as f:
        prog = json.load(f)

    for key in ("list_file", "created_at", "directories"):
        assert key in prog, f"Top-level key missing: {key}"

    assert len(prog["directories"]) == 1
    entry = prog["directories"][0]
    for field in ("source_dir", "output_dir", "profile", "status", "last_error"):
        assert field in entry, f"Per-directory field missing: {field}"

    assert entry["status"] == "done"
    assert entry["last_error"] is None


def test_batch_list_merges_new_dir(tmp_path):
    """A directory added to the list file between runs is picked up and processed on the next run."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    d2 = tmp_path / "course2"
    d2.mkdir()
    shutil.copy2(SAMPLE, d2 / "video.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(f"{d1}\n", encoding="utf-8")

    r1 = _run(["--list", str(list_file)])
    assert r1.returncode == 0

    list_file.write_text(f"{d1}\n{d2}\n", encoding="utf-8")

    r2 = _run(["--list", str(list_file)])
    assert r2.returncode == 0
    assert "Skipped (already done)" in r2.stdout

    with open(tmp_path / "courses.progress.json", encoding="utf-8") as f:
        prog = json.load(f)
    assert len(prog["directories"]) == 2
    assert all(d["status"] == "done" for d in prog["directories"])


def test_batch_list_default_profile_flag(tmp_path):
    """--profile sets the default profile for list entries that don't specify one."""
    d1 = tmp_path / "course1"
    d1.mkdir()
    shutil.copy2(SAMPLE, d1 / "video-sample.mp4")

    list_file = tmp_path / "courses.txt"
    list_file.write_text(f"{d1}\n", encoding="utf-8")  # no per-entry profile

    r = _run(["--list", str(list_file), "--profile", "480p-fast"])
    assert r.returncode == 0

    with open(tmp_path / "courses.progress.json", encoding="utf-8") as f:
        prog = json.load(f)
    assert prog["directories"][0]["profile"] == "480p-fast"
    assert prog["directories"][0]["status"] == "done"
