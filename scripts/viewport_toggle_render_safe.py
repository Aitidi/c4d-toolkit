"""Toggle Render Safe for the active viewport in Cinema 4D.

Usage:
- Open the Script Manager in Cinema 4D.
- Load or paste this script.
- Run it to toggle the current active viewport's Render Safe on/off.
- You can assign it to a shortcut for one-key access.
"""

import c4d


def main() -> None:
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        print("[c4d-toolkit] No active document.")
        return

    bd = doc.GetActiveBaseDraw()
    if bd is None:
        print("[c4d-toolkit] No active viewport found.")
        return

    current_state = bool(bd[c4d.BASEDRAW_DATA_RENDERSAFE])
    new_state = not current_state

    # Toggle Render Safe on the current active viewport.
    bd[c4d.BASEDRAW_DATA_RENDERSAFE] = new_state

    # If Render Safe is being enabled, also make sure safe frames are visible.
    if new_state and not bool(bd[c4d.BASEDRAW_DATA_SHOWSAFEFRAME]):
        bd[c4d.BASEDRAW_DATA_SHOWSAFEFRAME] = True

    c4d.EventAdd(c4d.EVENT_FORCEREDRAW)

    state_text = "ON" if new_state else "OFF"
    print(f"[c4d-toolkit] Active viewport Render Safe: {state_text}")


if __name__ == "__main__":
    main()
