# -*- coding: utf-8 -*-
import c4d

def is_empty_null(op: c4d.BaseObject) -> bool:
    """
    定义“空Null”的判定逻辑：
    1) 类型为 Null（c4d.Onull）
    2) 没有子物体（GetDown() is None）
    3) 没有标签（可按需放宽：如果你希望即使有标签也删，把这条去掉）
    """
    if op is None:
        return False
    if not op.CheckType(c4d.Onull):
        return False
    if op.GetDown() is not None:
        return False
    if op.GetFirstTag() is not None:
        return False
    return True

def collect_all_objects(first: c4d.BaseObject):
    """非递归遍历：用栈深度优先，返回从根到叶的线性列表。"""
    result = []
    stack = []
    op = first
    while op:
        result.append(op)
        # 先压 next，再压 down，这样弹栈时会先处理子层级（也可反过来）
        nxt = op.GetNext()
        if nxt:
            stack.append(nxt)
        down = op.GetDown()
        if down:
            stack.append(down)
        op = stack.pop() if stack else None
    return result

def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        return

    first = doc.GetFirstObject()
    if first is None:
        return

    all_objs = collect_all_objects(first)
    # 自底向上处理：反向遍历，先删叶子，避免父节点结构在过程中变化
    to_delete = []

    for op in reversed(all_objs):
        if is_empty_null(op):
            to_delete.append(op)

    if not to_delete:
        c4d.gui.MessageDialog("没有找到空的 Null。")
        return

    doc.StartUndo()
    try:
        for op in to_delete:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, op)
            op.Remove()
    finally:
        doc.EndUndo()

    c4d.EventAdd()
    c4d.gui.MessageDialog(f"已删除空的 Null：{len(to_delete)} 个。")

if __name__ == '__main__':
    main()
