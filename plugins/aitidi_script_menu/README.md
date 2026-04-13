# aitidi_script_menu

Cinema 4D 2026 Python plugin that adds a top-level menu named **Aitidi 脚本**.

## What it does

- Adds a dedicated top-level menu in the main menu bar.
- Scans configured script folders for `.py` scripts.
- If a script has a same-name icon file next to it (`.tif`, `.tiff`, `.png`, `.bmp`, `.jpg`, `.jpeg`), the menu item will display that icon.
- Creates one submenu per configured script folder.
- Lets you run each script directly from the menu.
- Adds an `打开 <folder>` entry at the top of each submenu.
- Adds four fixed utility entries at the top of the menu:
  - `打开 GitHub 脚本目录`
  - `更新脚本`
  - `刷新菜单 / 重载脚本`
  - `打开脚本文件夹`

## Default script location

This plugin now reads scripts from a **local runtime folder inside the plugin**:

- `%PLUGIN_DIR%\script`

That local folder is the plugin's read/update target. The repository source scripts can still stay in the repo's own `scripts/` directory.

## Config

Edit `aitidi_script_menu.config.json`:

```json
{
  "menuTitle": "Aitidi 脚本",
  "managedScriptsDir": "%PLUGIN_DIR%\\script",
  "sourceDirs": [
    "%PLUGIN_DIR%\\script"
  ],
  "githubRepoUrl": "https://github.com/Aitidi/c4d-toolkit",
  "githubOwner": "Aitidi",
  "githubRepo": "c4d-toolkit",
  "githubBranch": "main",
  "githubScriptsPath": "scripts"
}
```

## Notes

- `%PLUGIN_DIR%` will be resolved to the folder where this plugin is installed.
- `更新脚本` downloads `.py` files from the configured GitHub scripts path into `managedScriptsDir` and auto-refreshes the menu.
- `刷新菜单 / 重载脚本` will rescan the configured script folders and rebuild the menu without restarting Cinema 4D.
- If a menu item still does not appear after refreshing, restart Cinema 4D once to rule out host-side caching.
- Script files are executed as normal Python scripts with `c4d`, `doc`, `op`, `tp`, and `flags` injected.
- For script icons, place the image next to the script with the same base name, for example `安全框开关.py` + `安全框开关.tif`.
