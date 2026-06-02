import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("Python 3.11+ is required (tomllib not found).")

try:
    import msvcrt  # Windows only; absent on Linux/macOS — Ctrl+G detection is silently disabled

    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
ENCODE_JSON = "encode.json"
MAX_ATTEMPTS = 3
PROFILES_TOML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.toml")


class StopSignal:
    def __init__(self):
        self.requested = False
        self._listener_started = False

    def request(self):
        self.requested = True
        print("\n[!] Ctrl+G pressed — stopping after current file...", flush=True)

    def start_listener(self):
        if self._listener_started:
            return
        self._listener_started = True
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        while not self.requested:
            if _HAS_MSVCRT and msvcrt.kbhit() and msvcrt.getch() == b"\x07":
                self.request()
                break
            time.sleep(0.05)


def _find_videos(source_dir: str) -> list[str]:
    """Sorted list of absolute video paths in source_dir (non-recursive, files only)."""
    files = []
    for entry in os.scandir(source_dir):
        if entry.is_file() and os.path.splitext(entry.name)[1].lower() in VIDEO_EXTENSIONS:
            files.append(os.path.abspath(entry.path))
    return sorted(files)


def _progress_path(output_dir: str) -> str:
    return os.path.join(output_dir, ENCODE_JSON)


def _load_progress(output_dir: str) -> dict | None:
    path = _progress_path(output_dir)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_progress(output_dir: str, progress: dict) -> None:
    with open(_progress_path(output_dir), "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def _make_entry(input_abs: str, output_dir: str) -> dict:
    name = os.path.splitext(os.path.basename(input_abs))[0] + ".mp4"
    return {
        "input": input_abs,
        "output": os.path.join(output_dir, name),
        "status": "pending",
        "attempts": 0,
        "last_error": None,
    }


def _initialise_progress(source_dir: str, output_dir: str, video_files: list[str]) -> dict:
    existing = _load_progress(output_dir)

    if existing is None:
        progress = {
            "source_dir": os.path.abspath(source_dir),
            "output_dir": os.path.abspath(output_dir),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "files": [_make_entry(vf, output_dir) for vf in video_files],
        }
        _save_progress(output_dir, progress)
        return progress

    # Merge: add files discovered since the last run
    tracked = {e["input"] for e in existing["files"]}
    for vf in video_files:
        if vf not in tracked:
            existing["files"].append(_make_entry(vf, output_dir))
    _save_progress(output_dir, existing)
    return existing


def _load_profiles() -> tuple[dict, str]:
    """Load profiles.toml; returns (profiles_dict, default_name)."""
    if not os.path.exists(PROFILES_TOML):
        sys.exit(f"profiles.toml not found: {PROFILES_TOML}")
    with open(PROFILES_TOML, "rb") as f:
        data = tomllib.load(f)
    profiles = data.get("profiles", {})
    default = data.get("default", next(iter(profiles), None))
    if not profiles:
        sys.exit("No profiles defined in profiles.toml")
    if default not in profiles:
        sys.exit(f"Default profile '{default}' not found in profiles.toml")
    return profiles, default


def _run_ffpb(input_path: str, output_path: str, encode_args: list[str]) -> None:
    """Encodes input → output via ffpb. Raises RuntimeError on non-zero exit."""
    tmp = output_path + ".tmp.mp4"
    if os.path.exists(tmp):
        os.remove(tmp)

    cmd = ["ffpb", "-i", input_path, *encode_args, tmp]
    result = subprocess.run(cmd)

    if result.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"ffpb exited with code {result.returncode}")

    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(tmp, output_path)


def _print_summary(progress: dict) -> None:
    total = len(progress["files"])
    done = sum(1 for e in progress["files"] if e["status"] == "done")
    failed = sum(1 for e in progress["files"] if e["status"] == "failed")
    pending = total - done - failed
    print(f"\nSummary: {total} files — {done} done, {failed} failed, {pending} remaining")


def run_compress(
    source_dir: str, output_dir: str, encode_args: list[str], stop: StopSignal | None = None
) -> None:
    owned_stop = stop is None
    if owned_stop:
        stop = StopSignal()
        stop.start_listener()

    os.makedirs(output_dir, exist_ok=True)

    video_files = _find_videos(source_dir)
    if not video_files:
        print("No video files found.")
        return

    progress = _initialise_progress(source_dir, output_dir, video_files)
    files = progress["files"]

    print(f"Source:    {source_dir}")
    print(f"Output:    {output_dir}")
    print(f"Files:     {len(files)}")
    if owned_stop:
        print("Press Ctrl+G to stop gracefully after the current file.\n")

    for i, entry in enumerate(files):
        tag = f"[{i + 1}/{len(files)}]"
        name = os.path.basename(entry["input"])

        if entry["status"] == "done":
            print(f"{tag} Skipped (already done): {name}")
            continue

        if entry["attempts"] >= MAX_ATTEMPTS:
            print(f"{tag} Skipped (max attempts reached): {name}")
            continue

        if stop.requested:
            print("Stopping as requested.")
            break

        print(f"{tag} Compressing: {name}")
        entry["attempts"] += 1

        try:
            _run_ffpb(entry["input"], entry["output"], encode_args)
            entry["status"] = "done"
            entry["last_error"] = None
            print(f"     -> {os.path.basename(entry['output'])}")
        except Exception as exc:
            entry["last_error"] = str(exc)
            if entry["attempts"] >= MAX_ATTEMPTS:
                entry["status"] = "failed"
            print(f"     [!] Error: {exc}")

        _save_progress(output_dir, progress)

    _print_summary(progress)


def _parse_list_file(list_path: str) -> list[tuple[str, str | None]]:
    """Return (directory, profile_or_None) pairs from a batch list file; '#' lines are ignored."""
    entries = []
    with open(list_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            directory = parts[0]
            profile = parts[1].strip() if len(parts) > 1 else None
            entries.append((directory, profile))
    return entries


def _batch_progress_path(list_path: str) -> str:
    base = os.path.splitext(os.path.abspath(list_path))[0]
    return base + ".progress.json"


def _load_batch_progress(list_path: str) -> dict | None:
    path = _batch_progress_path(list_path)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_batch_progress(list_path: str, progress: dict) -> None:
    with open(_batch_progress_path(list_path), "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def _initialise_batch_progress(
    list_path: str, entries: list[tuple[str, str | None]], default_profile: str
) -> dict:
    existing = _load_batch_progress(list_path)

    def _make_dir_entry(raw_dir: str, profile: str | None) -> dict:
        abs_dir = os.path.abspath(raw_dir)
        return {
            "source_dir": abs_dir,
            "output_dir": os.path.join(abs_dir, "compressed"),
            "profile": profile or default_profile,
            "status": "pending",
            "last_error": None,
        }

    if existing is None:
        progress = {
            "list_file": os.path.abspath(list_path),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "directories": [_make_dir_entry(d, p) for d, p in entries],
        }
        _save_batch_progress(list_path, progress)
        return progress

    # Merge: preserve existing status; update profile; append new dirs
    tracked = {e["source_dir"]: e for e in existing["directories"]}
    for raw_dir, profile in entries:
        abs_dir = os.path.abspath(raw_dir)
        if abs_dir in tracked:
            tracked[abs_dir]["profile"] = profile or default_profile
        else:
            existing["directories"].append(_make_dir_entry(raw_dir, profile))
    _save_batch_progress(list_path, existing)
    return existing


def run_batch(list_path: str, profiles: dict, default_profile: str) -> None:
    if not os.path.isfile(list_path):
        sys.exit(f"Error: list file not found: {list_path}")

    entries = _parse_list_file(list_path)
    if not entries:
        print("No directories found in list file.")
        return

    progress = _initialise_batch_progress(list_path, entries, default_profile)
    dirs = progress["directories"]

    stop = StopSignal()
    stop.start_listener()

    print(f"List:      {list_path}")
    print(f"Dirs:      {len(dirs)}")
    print("Press Ctrl+G to stop gracefully after the current file.\n")

    for i, dir_entry in enumerate(dirs):
        tag = f"[{i + 1}/{len(dirs)}]"
        source_dir = dir_entry["source_dir"]
        profile_name = dir_entry["profile"]

        if dir_entry["status"] == "done":
            print(f"{tag} Skipped (already done): {source_dir}")
            continue

        if stop.requested:
            print("Stopping as requested.")
            break

        if profile_name not in profiles:
            msg = f"Unknown profile: {profile_name}"
            print(f"{tag} Skipped ({msg}): {source_dir}")
            dir_entry["status"] = "failed"
            dir_entry["last_error"] = msg
            _save_batch_progress(list_path, progress)
            continue

        output_dir = dir_entry["output_dir"]
        encode_args = profiles[profile_name]["args"]
        print(f"{tag} Processing: {source_dir}  [profile: {profile_name}]\n")

        try:
            run_compress(source_dir, output_dir, encode_args, stop=stop)
            dir_entry["status"] = "done"
            dir_entry["last_error"] = None
        except Exception as exc:
            dir_entry["status"] = "failed"
            dir_entry["last_error"] = str(exc)
            print(f"     [!] Directory error: {exc}")

        _save_batch_progress(list_path, progress)

    done = sum(1 for d in dirs if d["status"] == "done")
    failed = sum(1 for d in dirs if d["status"] == "failed")
    pending = len(dirs) - done - failed
    print(f"\nBatch summary: {len(dirs)} dirs — {done} done, {failed} failed, {pending} remaining")


def main() -> None:
    profiles, default_profile = _load_profiles()
    profile_names = list(profiles.keys())
    profile_lines = "\n".join(
        f"  {name:<16} {profiles[name]['description']}" for name in profile_names
    )

    parser = argparse.ArgumentParser(
        description="Batch-compress videos with ffpb (H.265) with resume support.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Profiles:\n"
            f"{profile_lines}\n\n"
            "Examples:\n"
            "  py compress.py D:/Videos/course_78\n"
            "  py compress.py D:/Videos/course_78 --output D:/Videos/course_78_x265\n"
            "  py compress.py D:/Videos/course_78 --profile 1080p\n"
            "  py compress.py --list courses.txt\n"
            "\n"
            "List file format (one entry per line, profile is optional):\n"
            "  D:/Videos/course_78\n"
            "  D:/Videos/course_79 1080p\n"
            "  # this line is a comment\n"
            "\n"
            "Outputs go to <course_dir>/compressed/ by default.\n"
            "Progress is saved to encode.json in the output directory.\n"
            "Batch progress is saved to <list-file>.progress.json.\n"
            "Press Ctrl+G to stop gracefully after the current file finishes."
        ),
    )
    parser.add_argument(
        "course_dir",
        nargs="?",
        help="Directory containing video files to compress",
    )
    parser.add_argument(
        "--list", "-l",
        metavar="FILE",
        help="Plain-text file listing directories to compress (one per line, optional profile)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory for single-dir mode (default: <course_dir>/compressed)",
    )
    parser.add_argument(
        "--profile", "-p",
        choices=profile_names,
        default=default_profile,
        metavar="PROFILE",
        help=f"Encoding profile (default: {default_profile}; choices: {', '.join(profile_names)})",
    )
    args = parser.parse_args()

    if args.list and args.course_dir:
        parser.error("--list and a positional directory are mutually exclusive")
    if not args.list and not args.course_dir:
        parser.error("provide a course directory or use --list FILE")

    try:
        if args.list:
            run_batch(args.list, profiles, args.profile)
        else:
            source_dir = os.path.abspath(args.course_dir)
            if not os.path.isdir(source_dir):
                sys.exit(f"Error: directory not found: {source_dir}")
            output_dir = (
                os.path.abspath(args.output)
                if args.output
                else os.path.join(source_dir, "compressed")
            )
            encode_args = profiles[args.profile]["args"]
            run_compress(source_dir, output_dir, encode_args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except RuntimeError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
