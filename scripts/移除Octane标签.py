import c4d

# 递归遍历对象
def iter_objects(op):
    while op:
        yield op
        for child in iter_objects(op.GetDown()):
            yield child
        op = op.GetNext()

def is_octane_tag(tag):
    if tag is None:
        return False

    # 1) 最可靠：插件 Tag（Octane 的标签通常是 Plugin 类型）
    # 用 Description 里拿到的 TypeName/Name 来判断是否带 Octane 字样
    try:
        bc = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
        if bc:
            dtype = bc.GetParameterI(c4d.DESC_TYPE_NAME)
            if dtype and isinstance(dtype, str):
                s = dtype.lower()
                if "octane" in s or "oct" in s:
                    return True
    except:
        pass

    # 2) 通过 Tag 的名字兜底（用户有时会改名，但很多默认仍含 Octane）
    try:
        name = tag.GetName() or ""
        s = name.lower()
        if "octane" in s or s.startswith("oct") or "oct " in s or " oct" in s:
            return True
    except:
        pass

    # 3) 通过 TagType / PluginID 兜底：Octane 的标签一般是“插件标签”
    # 这里不写死具体 ID（不同版本/分支可能不同），但可以用它来辅助判定
    try:
        if tag.CheckType(c4d.Tplugin):
            # Plugin ID 通常是一个较大的整数
            pid = tag.GetType()
            # 不直接 hardcode，但如果你愿意也可以打印 pid 来白名单/黑名单
            # 这里保持保守：仅凭 plugin 不删，避免误删其它插件的标签
            pass
    except:
        pass

    return False

def remove_octane_tags(doc):
    removed = 0

    # 处理对象标签
    for op in iter_objects(doc.GetFirstObject()):
        tag = op.GetFirstTag()
        while tag:
            nxt = tag.GetNext()
            if is_octane_tag(tag):
                tag.Remove()
                removed += 1
            tag = nxt

    # 处理材质标签（有些 Octane 的东西可能挂在材质或文档层）
    # 常见情况 Octane 主要是对象 Tag，所以这里主要做对象层即可。
    return removed

def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        return

    doc.StartUndo()

    removed = remove_octane_tags(doc)

    doc.EndUndo()
    c4d.EventAdd()

    c4d.gui.MessageDialog("删除完成：共删除 {} 个 Octane 相关标签。".format(removed))

if __name__ == "__main__":
    main()
