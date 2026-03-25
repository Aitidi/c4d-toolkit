import c4d
import json
import os
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
from c4d import gui, plugins

PLUGIN_MENU_NAMESPACE = 10698000
MENU_INSERT_ANCHOR = "M_EDITOR"
CONFIG_FILENAME = "aitidi_script_menu.config.json"


class ScriptCommand(plugins.CommandData):
    def __init__(self, script_path: str, label: str):
        self.script_path = script_path
        self.label = label

    def Execute(self, doc):
        if not os.path.isfile(self.script_path):
            gui.MessageDialog(f"找不到脚本：\n{self.script_path}")
            return False

        try:
            with open(self.script_path, "r", encoding="utf-8") as handle:
                source = handle.read()

            active_doc = doc or c4d.documents.GetActiveDocument()
            env = {
                "__name__": "__main__",
                "__file__": self.script_path,
                "__builtins__": __builtins__,
                "c4d": c4d,
                "gui": gui,
                "plugins": plugins,
                "doc": active_doc,
                "op": active_doc.GetActiveObject() if active_doc else None,
                "tp": active_doc.GetParticleSystem() if active_doc else None,
                "flags": 0,
            }
            exec(compile(source, self.script_path, "exec"), env, env)
            c4d.EventAdd()
            return True
        except Exception:
            traceback.print_exc()
            gui.MessageDialog(
                f"运行脚本失败：{self.label}\n\n{traceback.format_exc()}"
            )
            return False


class OpenFolderCommand(plugins.CommandData):
    def __init__(self, folder_path: str, label: str):
        self.folder_path = folder_path
        self.label = label

    def Execute(self, doc):
        if not os.path.isdir(self.folder_path):
            gui.MessageDialog(f"找不到目录：\n{self.folder_path}")
            return False
        c4d.storage.ShowInFinder(self.folder_path, False)
        return True


class OpenUrlCommand(plugins.CommandData):
    def __init__(self, url: str, label: str):
        self.url = url
        self.label = label

    def Execute(self, doc):
        try:
            return bool(webbrowser.open(self.url))
        except Exception:
            traceback.print_exc()
            gui.MessageDialog(
                f"打开链接失败：{self.label}\n\n{self.url}\n\n{traceback.format_exc()}"
            )
            return False


class UpdateScriptsCommand(plugins.CommandData):
    def __init__(self, github_config: dict, target_dir: str):
        self.github_config = dict(github_config)
        self.target_dir = target_dir

    def _fetch_json(self, url: str) -> dict:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "aitidi-script-menu/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _fetch_bytes(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "aitidi-script-menu/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def _iter_remote_scripts(self):
        owner = self.github_config["owner"]
        repo = self.github_config["repo"]
        branch = self.github_config["branch"]
        scripts_path = self.github_config["scriptsPath"].strip("/")

        tree_url = (
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/"
            f"{urllib.parse.quote(branch, safe='')}?recursive=1"
        )
        payload = self._fetch_json(tree_url)

        for item in payload.get("tree", []):
            if item.get("type") != "blob":
                continue

            remote_path = item.get("path", "")
            if not remote_path.startswith(scripts_path + "/"):
                continue

            relative_path = remote_path[len(scripts_path) + 1 :]
            if not relative_path.lower().endswith(".py"):
                continue
            if os.path.basename(relative_path).startswith("__"):
                continue

            raw_url = (
                f"https://raw.githubusercontent.com/{owner}/{repo}/"
                f"{urllib.parse.quote(branch, safe='')}/"
                f"{urllib.parse.quote(remote_path, safe='/')}"
            )
            yield relative_path, raw_url

    def Execute(self, doc):
        os.makedirs(self.target_dir, exist_ok=True)

        try:
            remote_scripts = list(self._iter_remote_scripts())
            if not remote_scripts:
                gui.MessageDialog("GitHub 上没有找到可更新的脚本。")
                return False

            new_count = 0
            updated_count = 0
            unchanged_count = 0

            for relative_path, raw_url in remote_scripts:
                local_path = os.path.join(self.target_dir, *relative_path.split("/"))
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                payload = self._fetch_bytes(raw_url)
                old_payload = None
                if os.path.isfile(local_path):
                    with open(local_path, "rb") as handle:
                        old_payload = handle.read()

                if old_payload == payload:
                    unchanged_count += 1
                    continue

                with open(local_path, "wb") as handle:
                    handle.write(payload)

                if old_payload is None:
                    new_count += 1
                else:
                    updated_count += 1

            _reload_runtime_state(update_menus=True)
            gui.MessageDialog(
                "脚本更新完成。\n\n"
                f"本地目录：\n{self.target_dir}\n\n"
                f"新增：{new_count}\n"
                f"更新：{updated_count}\n"
                f"未变化：{unchanged_count}\n\n"
                "菜单已自动刷新；如果仍未显示最新项，再重启一次 Cinema 4D。"
            )
            return True
        except urllib.error.HTTPError as exc:
            traceback.print_exc()
            gui.MessageDialog(
                "从 GitHub 更新脚本失败。\n\n"
                f"HTTP {exc.code}: {exc.reason}"
            )
            return False
        except Exception:
            traceback.print_exc()
            gui.MessageDialog(
                f"更新脚本失败。\n\n{traceback.format_exc()}"
            )
            return False


class RefreshMenuCommand(plugins.CommandData):
    def Execute(self, doc):
        try:
            _reload_runtime_state(update_menus=True)
            script_count = sum(len(group.get("entries", [])) for group in _MENU_TREE)
            gui.MessageDialog(
                "菜单已刷新。\n\n"
                f"脚本目录：{len(_MENU_TREE)}\n"
                f"脚本数量：{script_count}"
            )
            return True
        except Exception:
            traceback.print_exc()
            gui.MessageDialog(
                f"刷新菜单失败。\n\n{traceback.format_exc()}"
            )
            return False


_REGISTERED = False
_MENU_TITLE = "Aitidi 脚本"
_MENU_TREE = []
_UTILITY_COMMANDS = []
_COMMAND_LABELS = {}


def _plugin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _config_path() -> str:
    return os.path.join(_plugin_dir(), CONFIG_FILENAME)


def _replace_plugin_tokens(path: str) -> str:
    plugin_dir = _plugin_dir()
    return (
        path.replace("%PLUGIN_DIR%", plugin_dir)
        .replace("${PLUGIN_DIR}", plugin_dir)
        .replace("{PLUGIN_DIR}", plugin_dir)
    )


def _normalize(path: str) -> str:
    expanded = os.path.expandvars(path.strip())
    expanded = os.path.expanduser(expanded)
    expanded = _replace_plugin_tokens(expanded)
    return os.path.normpath(expanded)


def _load_config() -> dict:
    defaults = {
        "menuTitle": "Aitidi 脚本",
        "managedScriptsDir": r"%PLUGIN_DIR%\script",
        "sourceDirs": [r"%PLUGIN_DIR%\script"],
        "githubRepoUrl": "https://github.com/Aitidi/c4d-toolkit",
        "githubOwner": "Aitidi",
        "githubRepo": "c4d-toolkit",
        "githubBranch": "main",
        "githubScriptsPath": "scripts",
    }

    config_path = _config_path()
    if not os.path.isfile(config_path):
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            user_config = json.load(handle)
    except Exception:
        traceback.print_exc()
        return defaults

    merged = dict(defaults)
    if isinstance(user_config, dict):
        merged.update(user_config)
    return merged


def _display_name(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    return stem.replace("_", " ").replace("-", " ").strip() or stem


def _command_id(kind: str, value: str) -> int:
    key = f"{kind}:{value.lower()}"
    return PLUGIN_MENU_NAMESPACE + (zlib.crc32(key.encode("utf-8")) % 900000)


def _scan_scripts(source_dirs):
    groups = []
    for source_dir in source_dirs:
        root = _normalize(source_dir)
        if not os.path.isdir(root):
            continue

        entries = []
        for current_root, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            rel_dir = os.path.relpath(current_root, root)
            rel_dir = "" if rel_dir == "." else rel_dir

            for filename in sorted(filenames):
                if not filename.lower().endswith(".py"):
                    continue
                if filename.startswith("__"):
                    continue

                full_path = os.path.join(current_root, filename)
                label = _display_name(filename)
                if rel_dir:
                    path_label = rel_dir.replace(os.sep, " / ")
                    label = f"{path_label} / {label}"

                entries.append(
                    {
                        "kind": "script",
                        "id": _command_id("script", os.path.relpath(full_path, root)),
                        "label": label,
                        "path": full_path,
                    }
                )

        folder_name = os.path.basename(root.rstrip("\\/")) or root
        folder_cmd_id = _command_id("folder", root)
        groups.append(
            {
                "root": root,
                "title": folder_name,
                "folderCommand": {
                    "kind": "folder",
                    "id": folder_cmd_id,
                    "label": f"打开 {folder_name}",
                    "path": root,
                },
                "entries": sorted(entries, key=lambda item: item["label"].lower()),
            }
        )

    return groups


def _normalize_source_dirs(config: dict):
    managed_dir = _normalize(config.get("managedScriptsDir") or r"%PLUGIN_DIR%\script")
    source_dirs = [managed_dir]

    for source_dir in config.get("sourceDirs") or []:
        normalized = _normalize(source_dir)
        if normalized not in source_dirs:
            source_dirs.append(normalized)

    return managed_dir, source_dirs


def _github_web_folder_url(config: dict) -> str:
    repo_url = (config.get("githubRepoUrl") or "").rstrip("/")
    branch = config.get("githubBranch") or "main"
    scripts_path = (config.get("githubScriptsPath") or "").strip("/")

    if repo_url and scripts_path:
        return f"{repo_url}/tree/{branch}/{scripts_path}"
    if repo_url:
        return repo_url
    return "https://github.com/Aitidi/c4d-toolkit"


def _build_utility_commands(config: dict, managed_dir: str):
    github_config = {
        "owner": config.get("githubOwner") or "Aitidi",
        "repo": config.get("githubRepo") or "c4d-toolkit",
        "branch": config.get("githubBranch") or "main",
        "scriptsPath": config.get("githubScriptsPath") or "scripts",
    }

    github_folder_url = _github_web_folder_url(config)

    return [
        {
            "kind": "url",
            "id": _command_id("utility", "github-folder"),
            "label": "打开 GitHub 脚本目录",
            "url": github_folder_url,
        },
        {
            "kind": "update",
            "id": _command_id("utility", "update-scripts"),
            "label": "更新脚本",
            "targetDir": managed_dir,
            "github": github_config,
        },
        {
            "kind": "refresh",
            "id": _command_id("utility", "refresh-menu"),
            "label": "刷新菜单 / 重载脚本",
        },
        {
            "kind": "folder",
            "id": _command_id("utility", "open-local-scripts"),
            "label": "打开脚本文件夹",
            "path": managed_dir,
        },
    ]


def _reload_runtime_state(config=None, update_menus: bool = False):
    global _MENU_TITLE, _MENU_TREE, _UTILITY_COMMANDS

    current_config = config or _load_config()
    managed_dir, source_dirs = _normalize_source_dirs(current_config)
    os.makedirs(managed_dir, exist_ok=True)

    _MENU_TITLE = current_config.get("menuTitle") or "Aitidi 脚本"
    _UTILITY_COMMANDS = _build_utility_commands(current_config, managed_dir)
    _MENU_TREE = _scan_scripts(source_dirs)
    _register_commands(_MENU_TREE, _UTILITY_COMMANDS)

    if update_menus:
        c4d.gui.UpdateMenus()
        c4d.EventAdd()

    return managed_dir, source_dirs


def _register_command_plugin(command: dict):
    kind = command["kind"]
    cmd_id = int(command["id"])
    if cmd_id in _COMMAND_LABELS:
        return

    if kind == "folder":
        dat = OpenFolderCommand(command["path"], command["label"])
        help_text = f"打开目录：{command['path']}"
    elif kind == "url":
        dat = OpenUrlCommand(command["url"], command["label"])
        help_text = command["url"]
    elif kind == "update":
        dat = UpdateScriptsCommand(command["github"], command["targetDir"])
        help_text = f"从 GitHub 更新脚本到：{command['targetDir']}"
    elif kind == "refresh":
        dat = RefreshMenuCommand()
        help_text = "重新扫描脚本目录并刷新菜单"
    else:
        dat = ScriptCommand(command["path"], command["label"])
        help_text = command["path"]

    if plugins.RegisterCommandPlugin(
        id=cmd_id,
        str=command["label"],
        info=0,
        icon=None,
        help=help_text,
        dat=dat,
    ):
        _COMMAND_LABELS[cmd_id] = command["label"]


def _register_commands(menu_tree, utility_commands):
    for command in utility_commands:
        _register_command_plugin(command)

    for group in menu_tree:
        folder_cmd = group.get("folderCommand")
        if folder_cmd:
            _register_command_plugin(folder_cmd)

        for entry in group["entries"]:
            _register_command_plugin(entry)


def _build_submenu(group: dict):
    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, group["title"])

    folder_cmd = group.get("folderCommand")
    if folder_cmd:
        menu.InsData(c4d.MENURESOURCE_COMMAND, f"PLUGIN_CMD_{folder_cmd['id']}")
        menu.InsData(c4d.MENURESOURCE_SEPERATOR, True)

    if not group["entries"]:
        return menu

    for entry in group["entries"]:
        menu.InsData(c4d.MENURESOURCE_COMMAND, f"PLUGIN_CMD_{entry['id']}")
    return menu


def EnhanceMainMenu():
    if not _MENU_TREE and not _UTILITY_COMMANDS:
        return

    main_menu = gui.GetMenuResource(MENU_INSERT_ANCHOR)
    plugins_menu = gui.SearchPluginMenuResource()
    if main_menu is None:
        return

    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, _MENU_TITLE)

    for command in _UTILITY_COMMANDS:
        menu.InsData(c4d.MENURESOURCE_COMMAND, f"PLUGIN_CMD_{command['id']}")

    if _UTILITY_COMMANDS and _MENU_TREE:
        menu.InsData(c4d.MENURESOURCE_SEPERATOR, True)

    for group in _MENU_TREE:
        menu.InsData(c4d.MENURESOURCE_SUBMENU, _build_submenu(group))

    if plugins_menu:
        main_menu.InsDataAfter(c4d.MENURESOURCE_STRING, menu, plugins_menu)
    else:
        main_menu.InsData(c4d.MENURESOURCE_STRING, menu)


def PluginMessage(msg_id, data):
    if msg_id == c4d.C4DPL_BUILDMENU:
        EnhanceMainMenu()
    return False


def main():
    global _REGISTERED
    if _REGISTERED:
        return True

    _reload_runtime_state(update_menus=False)
    _REGISTERED = True
    return True


main()
