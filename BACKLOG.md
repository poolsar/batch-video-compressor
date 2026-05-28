# Backlog

Planned features and technical tasks not yet implemented.
Move completed items to `RELEASE_NOTES.md` with a timestamp.

---

## Encoding profile config

Create a named-profile config file (e.g. `profiles.toml`) that holds ffmpeg argument presets.
Each profile has a name, description, and argument list. A default profile is specified in the
config. The CLI gets a `--profile <name>` flag to select a non-default profile at runtime.

Example profiles: `720p-slow` (current default), `1080p`, `480p-fast`, `copy-audio`.

---
