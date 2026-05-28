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
        print("\n[!] Ctrl+G нажат — остановка после текущего файла...", flush=True)

    def start_listener(self):
        if self._listener_started:
            return
        self._listener_started = True
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        while not self.requested:
            if _HAS_MSVCRT and msvcrt.kbhit():
                if msvcrt.getch() == b"\x07":
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

    cmd = ["ffpb", "-i", input_path] + encode_args + [tmp]
    result = subprocess.run(cmd)

    if result.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"ffpb завершился с кодом {result.returncode}")

    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(tmp, output_path)


def _print_summary(progress: dict) -> None:
    total = len(progress["files"])
    done = sum(1 for e in progress["files"] if e["status"] == "done")
    failed = sum(1 for e in progress["files"] if e["status"] == "failed")
    pending = total - done - failed
    print(f"\nИтого: {total} файлов — {done} готово, {failed} ошибок, {pending} осталось")


def run_compress(source_dir: str, output_dir: str, encode_args: list[str]) -> None:
    os.makedirs(output_dir, exist_ok=True)

    video_files = _find_videos(source_dir)
    if not video_files:
        print("Видеофайлы не найдены.")
        return

    progress = _initialise_progress(source_dir, output_dir, video_files)
    files = progress["files"]

    stop = StopSignal()
    stop.start_listener()

    print(f"Источник:  {source_dir}")
    print(f"Вывод:     {output_dir}")
    print(f"Файлов:    {len(files)}")
    print("Нажмите Ctrl+G для остановки после текущего файла.\n")

    for i, entry in enumerate(files):
        tag = f"[{i + 1}/{len(files)}]"
        name = os.path.basename(entry["input"])

        if entry["status"] == "done":
            print(f"{tag} Пропущено (уже готово): {name}")
            continue

        if entry["attempts"] >= MAX_ATTEMPTS:
            print(f"{tag} Пропущено (макс. попытки): {name}")
            continue

        if stop.requested:
            print("Остановка по запросу.")
            break

        print(f"{tag} Сжатие: {name}")
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
            print(f"     [!] Ошибка: {exc}")

        _save_progress(output_dir, progress)

    _print_summary(progress)


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
            "\n"
            "Outputs go to <course_dir>/compressed/ by default.\n"
            "Progress is saved to encode.json in the output directory.\n"
            "Press Ctrl+G to stop gracefully after the current file finishes."
        ),
    )
    parser.add_argument("course_dir", help="Directory containing video files to compress")
    parser.add_argument(
        "--output", "-o",
        help="Output directory (default: <course_dir>/compressed)",
    )
    parser.add_argument(
        "--profile", "-p",
        choices=profile_names,
        default=default_profile,
        metavar="PROFILE",
        help=f"Encoding profile (default: {default_profile}; choices: {', '.join(profile_names)})",
    )
    args = parser.parse_args()

    source_dir = os.path.abspath(args.course_dir)
    if not os.path.isdir(source_dir):
        sys.exit(f"Ошибка: директория не найдена: {source_dir}")

    output_dir = (
        os.path.abspath(args.output) if args.output else os.path.join(source_dir, "compressed")
    )

    encode_args = profiles[args.profile]["args"]

    try:
        run_compress(source_dir, output_dir, encode_args)
    except KeyboardInterrupt:
        print("\nПрервано.")
    except RuntimeError as exc:
        sys.exit(f"Ошибка: {exc}")


if __name__ == "__main__":
    main()
