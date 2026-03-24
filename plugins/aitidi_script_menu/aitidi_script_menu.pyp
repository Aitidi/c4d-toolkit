import c4d
import json
import os
import traceback
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


_REGISTERED = False
_MENU_TITLE = "Aitidi Scripts"
_MENU_TREE = []
_COMMAND_LABELS = {}


def _plugin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _config_path() -> str:
    return os.path.join(_plugin_dir(), CONFIG_FILENAME)


def _normalize(path: str) -> str:
    return os.path.normpath(os.path.expandvars(path.strip()))


def _load_config() -> dict:
    config_path = _config_path()
    defaults = {
        "menuTitle": "Aitidi 脚本",
        "sourceDirs": [
            r"C:\Users\Aitid\Desktop\MyWorkspace\c4d-toolkit\scripts",
            r"C:\Users\Aitid\AppData\Roaming\Maxon\Maxon Cinema 4D 2026_1ABCDC12\library\scripts",
        ],
    }

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


def _register_commands(menu_tree):
    for group in menu_tree:
        folder_cmd = group.get("folderCommand")
        if folder_cmd:
            cmd_id = int(folder_cmd["id"])
            if cmd_id not in _COMMAND_LABELS:
                if plugins.RegisterCommandPlugin(
                    id=cmd_id,
                    str=folder_cmd["label"],
                    info=0,
                    icon=None,
                    help=f"打开目录：{folder_cmd['path']}",
                    dat=OpenFolderCommand(folder_cmd["path"], folder_cmd["label"]),
                ):
                    _COMMAND_LABELS[cmd_id] = folder_cmd["label"]

        for entry in group["entries"]:
            cmd_id = int(entry["id"])
            if cmd_id in _COMMAND_LABELS:
                continue
            if plugins.RegisterCommandPlugin(
                id=cmd_id,
                str=entry["label"],
                info=0,
                icon=None,
                help=entry["path"],
                dat=ScriptCommand(entry["path"], entry["label"]),
            ):
                _COMMAND_LABELS[cmd_id] = entry["label"]


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
    if not _MENU_TREE:
        return

    main_menu = gui.GetMenuResource(MENU_INSERT_ANCHOR)
    plugins_menu = gui.SearchPluginMenuResource()
    if main_menu is None:
        return

    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, _MENU_TITLE)

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
    global _REGISTERED, _MENU_TITLE, _MENU_TREE
    if _REGISTERED:
        return True

    config = _load_config()
    _MENU_TITLE = config.get("menuTitle") or "Aitidi 脚本"
    _MENU_TREE = _scan_scripts(config.get("sourceDirs") or [])
    _register_commands(_MENU_TREE)
    _REGISTERED = True
    return True


main()
