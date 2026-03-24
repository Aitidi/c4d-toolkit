# c4d-toolkit

A toolkit repository for **Cinema 4D** development resources, including plugins, scripts, utilities, and examples.

## Structure

- `plugins/` — C4D plugin projects (Python/C++).
- `scripts/` — repository source scripts for Cinema 4D and automation snippets.
- `plugins/aitidi_script_menu/` — the custom menu plugin.
- `plugins/aitidi_script_menu/script/` — local runtime script folder used by `aitidi_script_menu` after installation/update.
- `docs/` — notes, setup guides, and API references.
- `examples/` — minimal runnable demos.

## Getting Started

1. Choose your target C4D version and note API compatibility.
2. Put repository source scripts in `scripts/`.
3. Put plugin projects in `plugins/` (one folder per plugin).
4. `aitidi_script_menu` can download/sync scripts from GitHub `scripts/` into its local `script/` folder.
5. Document usage in `docs/`.

## Naming Suggestions

- Plugin folder: `plugins/<plugin-name>/`
- Script file: `scripts/<category>_<task>.py`
- Plugin local runtime script: `plugins/<plugin-name>/script/<task>.py`

## License

MIT (adjust if needed).
