# -*- coding: utf-8 -*-
"""
将活动物体的参数、用户数据、标签和关键帧尽量完整复制到另一个同类型物体。

用法：
1. 在对象管理器中选中“源物体”，并让它成为活动对象。
2. 在 Script Manager 中运行本脚本。
3. 脚本会弹出同类型物体列表，请选择“目标物体”。

说明：
- 目标物体的名称、父级、子级和对象管理器位置会保留。
- 目标物体原有动画轨道、用户数据和标签会先清空，再从源物体复制。
- 普通参数会通过 C4D Description 逐项复制，不依赖关键帧轨道。
- C4D API 无法公开访问或不可克隆的内部状态会被跳过，并在控制台打印提示。
"""

import c4d
from c4d import gui


def ShowError(message):
    """弹出中文错误提示。"""
    gui.MessageDialog(message)
    print("[复制参数和关键帧] 错误：{0}".format(message))


def IterObjects(root):
    """深度优先遍历对象层级。"""
    obj = root
    while obj is not None:
        yield obj
        child = obj.GetDown()
        if child is not None:
            for child_obj in IterObjects(child):
                yield child_obj
        obj = obj.GetNext()


def CollectCompatibleTargets(doc, source):
    """收集文档中所有和源对象同类型、且不是源对象本身的目标候选。"""
    first = doc.GetFirstObject()
    if first is None:
        return []

    source_type = source.GetType()
    return [
        obj for obj in IterObjects(first)
        if obj is not source and obj.GetType() == source_type
    ]


def ChooseTargetObject(doc, source):
    """弹出对象选择列表，让用户选择目标对象。"""
    candidates = CollectCompatibleTargets(doc, source)
    if not candidates:
        ShowError("当前文档中没有找到其它同类型物体，无法选择目标物体。")
        return None

    gui.MessageDialog(
        "源物体：{0}\n\n请在接下来弹出的列表中选择目标物体。".format(source.GetName()),
        c4d.GEMB_OK | c4d.GEMB_ICONASTERISK
    )

    choice = gui.SelectionListDialog(candidates, doc, c4d.MOUSEPOS, c4d.MOUSEPOS)
    if choice == c4d.NOTOK:
        print("[复制参数和关键帧] 已取消目标物体选择。")
        return None

    if choice < 0 or choice >= len(candidates):
        ShowError("目标物体选择结果无效。")
        return None

    return candidates[choice]


def GetSourceAndTarget(doc):
    """返回活动对象作为源、弹窗选择的对象作为目标。"""
    source = doc.GetActiveObject()
    if source is None:
        ShowError("请先选中一个源物体，并让它成为活动对象。")
        return None, None

    target = ChooseTargetObject(doc, source)
    if target is None:
        return None, None

    return source, target


def RemoveTracks(node):
    """移除 BaseList2D 节点上的所有动画轨道。"""
    track = node.GetFirstCTrack()
    while track is not None:
        next_track = track.GetNext()
        try:
            track.Remove()
        except Exception as error:
            print("[复制参数和关键帧] 跳过无法移除的动画轨道：{0}".format(error))
        track = next_track


def CopyTracks(source_node, target_node):
    """复制 BaseList2D 节点上的所有动画轨道。"""
    for track in source_node.GetCTracks():
        try:
            cloned_track = track.GetClone()
            if cloned_track is None:
                print("[复制参数和关键帧] 跳过无法克隆的动画轨道。")
                continue
            target_node.InsertTrackSorted(cloned_track)
        except Exception as error:
            print("[复制参数和关键帧] 跳过无法复制的动画轨道：{0}".format(error))


def RemoveUserData(node):
    """移除节点上的全部用户数据。"""
    user_data = list(node.GetUserDataContainer())
    for desc_id, _container in reversed(user_data):
        try:
            node.RemoveUserData(desc_id)
        except Exception as error:
            print("[复制参数和关键帧] 跳过无法移除的用户数据：{0}".format(error))


def CopyUserData(source_node, target_node):
    """复制用户数据定义和值，并尽量保持 DescID 兼容以承接动画轨道。"""
    for desc_id, container in source_node.GetUserDataContainer():
        try:
            new_desc_id = target_node.AddUserData(container.GetClone())
            if new_desc_id is None:
                print("[复制参数和关键帧] 跳过无法创建的用户数据。")
                continue
            target_node[new_desc_id] = source_node[desc_id]
        except Exception as error:
            print("[复制参数和关键帧] 跳过无法复制的用户数据：{0}".format(error))


def RemoveTags(target):
    """清空目标对象上的标签。"""
    for tag in list(target.GetTags()):
        try:
            tag.Remove()
        except Exception as error:
            print("[复制参数和关键帧] 跳过无法移除的标签 {0}：{1}".format(tag.GetName(), error))


def CopyTags(source, target):
    """复制源对象上的所有标签，包含材质标签和标签动画。"""
    previous_tag = None
    for tag in source.GetTags():
        try:
            cloned_tag = tag.GetClone(c4d.COPYFLAGS_0)
            if cloned_tag is None:
                print("[复制参数和关键帧] 跳过无法克隆的标签：{0}".format(tag.GetName()))
                continue

            if previous_tag is None:
                target.InsertTag(cloned_tag)
            else:
                target.InsertTag(cloned_tag, previous_tag)
            previous_tag = cloned_tag
        except Exception as error:
            print("[复制参数和关键帧] 跳过无法复制的标签 {0}：{1}".format(tag.GetName(), error))


def GetParameterName(container, desc_id):
    """尽量取得参数中文/界面名称，用于控制台提示。"""
    try:
        name = container.GetString(c4d.DESC_NAME)
        if name:
            return name
    except Exception:
        pass
    return str(desc_id)


def IsSkippedObjectParameter(desc_id):
    """这些属性属于目标对象身份或不适合直接写入。"""
    try:
        first_level = desc_id[0].id
    except Exception:
        return False

    return first_level in {
        c4d.ID_BASELIST_NAME,
    }


def CopyDescriptionParameters(source_node, target_node):
    """按 Description 遍历并复制所有可访问、可写入的普通参数。"""
    try:
        description = source_node.GetDescription(c4d.DESCFLAGS_DESC_0)
    except Exception as error:
        print("[复制参数和关键帧] 无法读取参数描述：{0}".format(error))
        return

    copied_count = 0
    skipped_count = 0

    for container, desc_id, _group_id in description:
        if IsSkippedObjectParameter(desc_id):
            skipped_count += 1
            continue

        try:
            value = source_node.GetParameter(desc_id, c4d.DESCFLAGS_GET_0)
        except Exception:
            skipped_count += 1
            continue

        try:
            if target_node.SetParameter(desc_id, value, c4d.DESCFLAGS_SET_0):
                copied_count += 1
            else:
                skipped_count += 1
                print(
                    "[复制参数和关键帧] 跳过不可写入的参数：{0}".format(
                        GetParameterName(container, desc_id)
                    )
                )
        except Exception as error:
            skipped_count += 1
            print(
                "[复制参数和关键帧] 跳过无法复制的参数 {0}：{1}".format(
                    GetParameterName(container, desc_id),
                    error
                )
            )

    print(
        "[复制参数和关键帧] 普通参数复制完成：成功 {0} 项，跳过 {1} 项。".format(
            copied_count,
            skipped_count
        )
    )


def CopyObjectData(source, target):
    """复制对象参数容器和 Description 参数，同时保留目标对象名称。"""
    target_name = target.GetName()
    try:
        source_data = source.GetData().GetClone()
        target.SetData(source_data)
    except Exception as error:
        print("[复制参数和关键帧] 对象参数容器复制失败，改用逐项复制：{0}".format(error))
        source_data = source.GetData()
        target_data = target.GetDataInstance()
        for key in source_data:
            try:
                target_data[key] = source_data[key]
            except Exception as item_error:
                print("[复制参数和关键帧] 跳过无法复制的参数 {0}：{1}".format(key, item_error))

    CopyDescriptionParameters(source, target)
    target.SetName(target_name)


def CopyEverything(source, target):
    """按既定策略从源对象复制到目标对象。"""
    RemoveTracks(target)
    RemoveUserData(target)
    RemoveTags(target)

    CopyObjectData(source, target)
    CopyUserData(source, target)
    CopyTracks(source, target)
    CopyTags(source, target)


def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        ShowError("没有找到当前 C4D 文档。")
        return

    source, target = GetSourceAndTarget(doc)
    if source is None or target is None:
        return

    doc.StartUndo()
    try:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, target)
        for tag in target.GetTags():
            doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, tag)

        CopyEverything(source, target)

        doc.AddUndo(c4d.UNDOTYPE_CHANGE, target)
        print("[复制参数和关键帧] 已从“{0}”复制到“{1}”。".format(source.GetName(), target.GetName()))
    except Exception as error:
        ShowError("复制过程中发生错误：{0}".format(error))
    finally:
        doc.EndUndo()
        c4d.EventAdd()


if __name__ == "__main__":
    main()
