# aitidi_script_menu

Cinema 4D 2026 Python plugin that adds a top-level menu named **Aitidi 脚本**.

## What it does

- Adds a dedicated top-level menu in the main menu bar.
- Scans configured script folders for `.py` scripts.
- Creates one submenu per configured script folder.
- Lets you run each script directly from the menu.
- Adds an `打开 <folder>` entry at the top of each submenu.

## Config

Edit `aitidi_script_menu.config.json`:

```json
{
  "menuTitle": "Aitidi 脚本",
  "sourceDirs": [
    "C:\\Users\\Aitid\\Desktop\\MyWorkspace\\c4d-toolkit\\scripts",
    "C:\\Users\\Aitid\\AppData\\Roaming\\Maxon\\Maxon Cinema 4D 2026_1ABCDC12\\library\\scripts"
  ]
}
```

## Notes

- Restart Cinema 4D after adding/removing scripts so the menu rebuilds from startup.
- Script files are executed as normal Python scripts with `c4d`, `doc`, `op`, `tp`, and `flags` injected.
