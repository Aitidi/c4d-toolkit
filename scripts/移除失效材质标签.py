# -*- coding: utf-8 -*-
"""
清除当前文档中失效的材质标签。

会删除以下材质标签：
- 没有绑定材质的材质标签。
- 绑定的材质不在当前文档材质列表中的材质标签。

脚本只删除材质标签，不删除材质、不删除对象，也不会修改有效材质标签。
"""

import c4d
from c4d import gui


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


def CollectDocumentMaterials(doc):
    """收集当前文档中的所有材质对象。"""
    materials = []
    mat = doc.GetFirstMaterial()
    while mat is not None:
        materials.append(mat)
        mat = mat.GetNext()
    return materials


def IsInvalidMaterialTag(tag, document_materials):
    """判断材质标签是否失效。"""
    if tag is None or not tag.CheckType(c4d.Ttexture):
        return False

    material = tag[c4d.TEXTURETAG_MATERIAL]
    if material is None:
        return True

    return material not in document_materials


def CollectInvalidMaterialTags(doc):
    """返回 [(object, tag), ...] 形式的失效材质标签列表。"""
    invalid_tags = []
    document_materials = CollectDocumentMaterials(doc)
    first_obj = doc.GetFirstObject()

    if first_obj is None:
        return invalid_tags

    for obj in IterObjects(first_obj):
        tag = obj.GetFirstTag()
        while tag is not None:
            next_tag = tag.GetNext()
            if IsInvalidMaterialTag(tag, document_materials):
                invalid_tags.append((obj, tag))
            tag = next_tag

    return invalid_tags


def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        gui.MessageDialog("没有找到当前文档。")
        return

    invalid_tags = CollectInvalidMaterialTags(doc)
    if not invalid_tags:
        gui.MessageDialog("没有找到失效的材质标签。")
        return

    doc.StartUndo()
    try:
        for obj, tag in invalid_tags:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, tag)
            print("[清除失效材质标签] 删除：对象「{0}」上的材质标签「{1}」".format(
                obj.GetName(), tag.GetName()
            ))
            tag.Remove()
    finally:
        doc.EndUndo()

    c4d.EventAdd()
    gui.MessageDialog("已清除失效的材质标签：{0} 个。".format(len(invalid_tags)))


if __name__ == "__main__":
    main()
