import c4d
import json
import os
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
from c4d import bitmaps, gui, plugins

PLUGIN_MENU_NAMESPACE = 10698000
MAIN_COMMAND_ID = 10698090
MENU_INSERT_ANCHOR = "M_EDITOR"
CONFIG_FILENAME = "aitidi_script_menu.config.json"
SCRIPT_ICON_EXTENSIONS = (".tif", ".tiff", ".png", ".bmp", ".jpg", ".jpeg")

_MENU_TITLE = "Aitidi 脚本"
_MENU_TREE = []
_UTILITY_COMMANDS = []
_RUNTIME_COMMANDS_BY_ID = {}
_REGISTERED_SCRIPT_ICONS = {}
_REGISTERED_SCRIPT_BITMAPS = {}
_REGISTERED = False


class DynamicMenuCommand(plugins.CommandData):
    def Execute(self, doc):
        return _refresh_menu(show_dialog=True)

    def GetSubContainer(self, doc, submenu):
        _reload_runtime_state(update_menus=False)
        return _populate_dynamic_menu(submenu)

    def ExecuteSubID(self, doc, subid):
        _reload_runtime_state(update_menus=False)
        command = _RUNTIME_COMMANDS_BY_ID.get(int(subid))
        if not command:
            gui.MessageDialog(f"找不到菜单项：{subid}")
            return False
        return _execute_runtime_command(command, doc)

    def GetScriptName(self):
        return "aitidi_script_menu.dynamic_menu"



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
    return PLUGIN_MENU_NAMESPACE + 100 + (zlib.crc32(key.encode("utf-8")) % 899000)



def _script_icon_id(value: str) -> int:
    key = f"icon:{value.lower()}"
    return PLUGIN_MENU_NAMESPACE + 1000000 + (zlib.crc32(key.encode("utf-8")) % 899000)



def _find_script_icon_path(script_path: str):
    stem, _ = os.path.splitext(script_path)
    for extension in SCRIPT_ICON_EXTENSIONS:
        icon_path = stem + extension
        if os.path.isfile(icon_path):
            return icon_path
    return None



def _ensure_script_icon_registered(icon_path: str):
    normalized_path = os.path.normcase(os.path.normpath(icon_path))

    try:
        mtime = os.path.getmtime(normalized_path)
    except OSError:
        return None

    cached = _REGISTERED_SCRIPT_ICONS.get(normalized_path)
    if cached and cached.get("mtime") == mtime:
        return cached.get("id")

    bitmap = bitmaps.BaseBitmap()
    result = bitmap.InitWith(normalized_path)
    if not result or result[0] != c4d.IMAGERESULT_OK:
        return None

    icon_id = _script_icon_id(normalized_path)
    gui.RegisterIcon(icon_id, bitmap)
    _REGISTERED_SCRIPT_ICONS[normalized_path] = {"id": icon_id, "mtime": mtime}
    _REGISTERED_SCRIPT_BITMAPS[icon_id] = bitmap
    return icon_id



def _menu_label(label: str, icon_id=None) -> str:
    if icon_id:
        # Cinema 4D supports inline icon markers in dynamic menu labels: &i<iconId>&
        return f"{label}&i{int(icon_id)}&"
    return label



def _normalize_source_dirs(config: dict):
    managed_dir = _normalize(config.get("managedScriptsDir") or r"%PLUGIN_DIR%\script")
    source_dirs = [managed_dir]

    for source_dir in config.get("sourceDirs") or []:
        normalized = _normalize(source_dir)
        if normalized not in source_dirs:
            source_dirs.append(normalized)

    return managed_dir, source_dirs



def _scan_scripts(source_dirs):
    normalized_roots = []
    for source_dir in source_dirs:
        root = _normalize(source_dir)
        if os.path.isdir(root):
            normalized_roots.append(root)

    groups = []

    for root in normalized_roots:
        folder_name = os.path.basename(root.rstrip("\\/")) or root
        tree_root = {
            "kind": "folder",
            "title": folder_name,
            "children": [],
            "_folders": {},
        }
        script_count = 0

        for current_root, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            rel_dir = os.path.relpath(current_root, root)
            rel_dir = "" if rel_dir == "." else rel_dir

            parent = tree_root
            if rel_dir:
                for part in rel_dir.split(os.sep):
                    folders = parent.setdefault("_folders", {})
                    if part not in folders:
                        folders[part] = {
                            "kind": "folder",
                            "title": part,
                            "children": [],
                            "_folders": {},
                        }
                    parent = folders[part]

            for filename in sorted(filenames):
                if not filename.lower().endswith(".py"):
                    continue
                if filename.startswith("__"):
                    continue

                full_path = os.path.join(current_root, filename)
                icon_path = _find_script_icon_path(full_path)
                icon_id = (
                    _ensure_script_icon_registered(icon_path)
                    if icon_path
                    else None
                )
                parent["children"].append(
                    {
                        "kind": "script",
                        "id": _command_id("script", full_path),
                        "label": _display_name(filename),
                        "path": full_path,
                        "iconId": icon_id,
                    }
                )
                script_count += 1

        finalized_root = _finalize_folder_node(tree_root)
        groups.append(
            {
                "root": root,
                "title": folder_name,
                "children": finalized_root.get("children", []),
                "scriptCount": script_count,
            }
        )

    return groups



def _finalize_folder_node(node: dict):
    folder_children = [
        _finalize_folder_node(child)
        for child in node.pop("_folders", {}).values()
    ]
    folder_children.sort(key=lambda item: item["title"].lower())

    script_children = sorted(
        node.get("children", []),
        key=lambda item: item["label"].lower(),
    )

    node["children"] = folder_children + script_children
    return node



def _github_web_folder_url(config: dict) -> str:
    repo_url = (config.get("githubRepoUrl") or "").rstrip("/")
    branch = config.get("githubBranch") or "main"
    scripts_path = (config.get("githubScriptsPath") or "").strip("/")

    if repo_url and scripts_path:
        return f"{repo_url}/tree/{branch}/{scripts_path}"
    if repo_url:
        return repo_url
    return "https://github.com/Aitidi/c4d-toolkit"



def _build_runtime_commands(config: dict, managed_dir: str, menu_tree):
    github_config = {
        "owner": config.get("githubOwner") or "Aitidi",
        "repo": config.get("githubRepo") or "c4d-toolkit",
        "branch": config.get("githubBranch") or "main",
        "scriptsPath": config.get("githubScriptsPath") or "scripts",
    }

    return [
        {
            "kind": "url",
            "id": _command_id("utility", "github-folder"),
            "label": "打开 GitHub 脚本目录",
            "url": _github_web_folder_url(config),
        },
        {
            "kind": "update",
            "id": _command_id("utility", "update-scripts"),
            "label": "同步 GitHub 脚本",
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
            "label": "打开本地脚本目录",
            "path": managed_dir,
        },
    ]



def _collect_script_commands(menu_tree):
    commands = []

    def walk(nodes):
        for node in nodes:
            if node["kind"] == "script":
                commands.append(node)
            elif node["kind"] == "folder":
                walk(node.get("children", []))

    for group in menu_tree:
        walk(group.get("children", []))

    return commands



def _append_menu_nodes(container, nodes):
    has_entries = False

    for node in nodes:
        if node["kind"] == "script":
            container.InsData(
                int(node["id"]),
                _menu_label(node["label"], node.get("iconId")),
            )
            has_entries = True
            continue

        if node["kind"] == "folder":
            sub_container = c4d.BaseContainer()
            sub_container.SetString(1, node["title"])
            if _append_menu_nodes(sub_container, node.get("children", [])):
                container.InsData(0, sub_container)
                has_entries = True

    return has_entries



def _populate_dynamic_menu(submenu):
    has_utility_entries = False
    for command in _UTILITY_COMMANDS:
        submenu.InsData(int(command["id"]), command["label"])
        has_utility_entries = True

    script_groups = [group for group in _MENU_TREE if group.get("scriptCount", 0) > 0]
    if not script_groups:
        return has_utility_entries

    if has_utility_entries:
        submenu.InsData(0, "")

    if len(script_groups) == 1:
        has_script_entries = _append_menu_nodes(
            submenu, script_groups[0].get("children", [])
        )
    else:
        has_script_entries = False
        for group in script_groups:
            sub_container = c4d.BaseContainer()
            sub_container.SetString(1, group["title"])
            if _append_menu_nodes(sub_container, group.get("children", [])):
                submenu.InsData(0, sub_container)
                has_script_entries = True

    return has_utility_entries or has_script_entries



def _reload_runtime_state(config=None, update_menus: bool = False):
    global _MENU_TITLE, _MENU_TREE, _UTILITY_COMMANDS, _RUNTIME_COMMANDS_BY_ID

    current_config = config or _load_config()
    managed_dir, source_dirs = _normalize_source_dirs(current_config)
    os.makedirs(managed_dir, exist_ok=True)

    _MENU_TITLE = current_config.get("menuTitle") or "Aitidi 脚本"
    _MENU_TREE = _scan_scripts(source_dirs)
    _UTILITY_COMMANDS = _build_runtime_commands(current_config, managed_dir, _MENU_TREE)
    script_commands = _collect_script_commands(_MENU_TREE)
    _RUNTIME_COMMANDS_BY_ID = {
        int(command["id"]): command
        for command in (_UTILITY_COMMANDS + script_commands)
    }

    if update_menus:
        c4d.gui.UpdateMenus()
        c4d.EventAdd()

    return managed_dir, source_dirs



def _execute_script(script_path: str, label: str, doc):
    if not os.path.isfile(script_path):
        gui.MessageDialog(f"找不到脚本：\n{script_path}")
        return False

    try:
        with open(script_path, "r", encoding="utf-8") as handle:
            source = handle.read()

        active_doc = doc or c4d.documents.GetActiveDocument()
        env = {
            "__name__": "__main__",
            "__file__": script_path,
            "__builtins__": __builtins__,
            "c4d": c4d,
            "gui": gui,
            "plugins": plugins,
            "doc": active_doc,
            "op": active_doc.GetActiveObject() if active_doc else None,
            "tp": active_doc.GetParticleSystem() if active_doc else None,
            "flags": 0,
        }
        exec(compile(source, script_path, "exec"), env, env)
        c4d.EventAdd()
        return True
    except Exception:
        traceback.print_exc()
        gui.MessageDialog(
            f"运行脚本失败：{label}\n\n{traceback.format_exc()}"
        )
        return False



def _open_folder(folder_path: str, label: str):
    if not os.path.isdir(folder_path):
        gui.MessageDialog(f"找不到目录：\n{folder_path}")
        return False

    try:
        if os.name == "nt":
            os.startfile(folder_path)
        else:
            c4d.storage.ShowInFinder(folder_path, False)
        return True
    except Exception:
        traceback.print_exc()
        gui.MessageDialog(
            f"打开目录失败：{label}\n\n{traceback.format_exc()}"
        )
        return False



def _open_url(url: str, label: str):
    try:
        return bool(webbrowser.open(url))
    except Exception:
        traceback.print_exc()
        gui.MessageDialog(
            f"打开链接失败：{label}\n\n{url}\n\n{traceback.format_exc()}"
        )
        return False



def _fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "aitidi-script-menu/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))



def _fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "aitidi-script-menu/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()



def _iter_remote_scripts(github_config: dict):
    owner = github_config["owner"]
    repo = github_config["repo"]
    branch = github_config["branch"]
    scripts_path = github_config["scriptsPath"].strip("/")

    tree_url = (
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/"
        f"{urllib.parse.quote(branch, safe='')}?recursive=1"
    )
    payload = _fetch_json(tree_url)

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



def _sync_scripts(github_config: dict, target_dir: str):
    os.makedirs(target_dir, exist_ok=True)

    try:
        remote_scripts = list(_iter_remote_scripts(github_config))
        if not remote_scripts:
            gui.MessageDialog("GitHub 上没有找到可同步的脚本。")
            return False

        new_count = 0
        updated_count = 0
        unchanged_count = 0

        for relative_path, raw_url in remote_scripts:
            local_path = os.path.join(target_dir, *relative_path.split("/"))
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            payload = _fetch_bytes(raw_url)
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
            "脚本同步完成。\n\n"
            f"本地目录：\n{target_dir}\n\n"
            f"新增：{new_count}\n"
            f"更新：{updated_count}\n"
            f"未变化：{unchanged_count}\n\n"
            "菜单已自动刷新，无需重启 Cinema 4D。"
        )
        return True
    except urllib.error.HTTPError as exc:
        traceback.print_exc()
        gui.MessageDialog(
            "从 GitHub 同步脚本失败。\n\n"
            f"HTTP {exc.code}: {exc.reason}"
        )
        return False
    except Exception:
        traceback.print_exc()
        gui.MessageDialog(
            f"同步脚本失败。\n\n{traceback.format_exc()}"
        )
        return False



def _refresh_menu(show_dialog: bool = True):
    try:
        _reload_runtime_state(update_menus=True)
        if show_dialog:
            script_count = sum(group.get("scriptCount", 0) for group in _MENU_TREE)
            gui.MessageDialog(
                "菜单已刷新。\n\n"
                f"脚本目录：{len(_MENU_TREE)}\n"
                f"脚本数量：{script_count}\n\n"
                "新增、删除、重命名脚本已可直接生效。"
            )
        return True
    except Exception:
        traceback.print_exc()
        gui.MessageDialog(
            f"刷新菜单失败。\n\n{traceback.format_exc()}"
        )
        return False



def _execute_runtime_command(command: dict, doc):
    kind = command["kind"]

    if kind == "script":
        return _execute_script(command["path"], command["label"], doc)
    if kind == "folder":
        return _open_folder(command["path"], command["label"])
    if kind == "url":
        return _open_url(command["url"], command["label"])
    if kind == "update":
        return _sync_scripts(command["github"], command["targetDir"])
    if kind == "refresh":
        return _refresh_menu(show_dialog=True)

    gui.MessageDialog(f"未知菜单项类型：{kind}")
    return False



def EnhanceMainMenu():
    main_menu = gui.GetMenuResource(MENU_INSERT_ANCHOR)
    plugins_menu = gui.SearchPluginMenuResource()
    if main_menu is None:
        return

    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, _MENU_TITLE)
    menu.InsData(c4d.MENURESOURCE_COMMAND, f"PLUGIN_CMD_{MAIN_COMMAND_ID}")

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

    if not plugins.RegisterCommandPlugin(
        id=MAIN_COMMAND_ID,
        str="Aitidi Script Menu",
        info=0,
        icon=None,
        help="Aitidi 脚本动态菜单",
        dat=DynamicMenuCommand(),
    ):
        return False

    _REGISTERED = True
    return True


main()
