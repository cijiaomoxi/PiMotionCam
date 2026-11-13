"""极简 HTML 结构分析：把模板切成「元素 / 文本 / 注释」事件，并维护元素嵌套。

只服务于一件事——给中文文案打 `data-i18n` 标记时，需要知道：
  * 这段文字属于哪个元素；
  * 该元素内部是否还有别的子元素（有子元素就只能包 span，不能直接改 innerHTML）。

自己写而不是用 html.parser，是因为要拿到**字节偏移**，好在原文件上做
最小侵入的文本替换，保证模板除标记外一字不改。
"""
from __future__ import annotations

import re

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
# 内容原样保留、不做 i18n 处理的标签
RAW_TAGS = {"script", "style"}

_TAG_NAME = re.compile(r"</?\s*([A-Za-z][\w:-]*)")


class Node:
    """一个 HTML 元素。"""

    __slots__ = ("name", "tag_start", "tag_end", "content_start", "content_end",
                 "children", "texts", "parent", "tag_src")

    def __init__(self, name, tag_start, tag_end, tag_src, parent):
        self.name = name
        self.tag_start = tag_start      # '<' 位置
        self.tag_end = tag_end          # '>' 之后的位置
        self.tag_src = tag_src          # 整个开始标签原文
        self.content_start = tag_end    # 内容起点
        self.content_end = tag_end      # 内容终点（遇到对应结束标签时更新）
        self.children: list["Node"] = []
        self.texts: list[tuple[int, int]] = []   # 直接子文本节点区间
        self.parent = parent

    @property
    def has_element_children(self) -> bool:
        return bool(self.children)

    def attr_insert_pos(self) -> int:
        """在开始标签里插入新属性的位置（末尾 '>' 或 '/>' 之前）。"""
        s = self.tag_src.rstrip()
        if s.endswith("/>"):
            return self.tag_start + len(s) - 2
        return self.tag_start + len(s) - 1


def _find_tag_end(src: str, lt: int) -> int:
    """从 '<' 开始找到标签结束的 '>'（跳过引号内的 '>'）。"""
    n = len(src)
    j = lt + 1
    quote = None
    while j < n:
        c = src[j]
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == ">":
            return j + 1
        j += 1
    return n


def parse(src: str):
    """解析 HTML，返回 (root_nodes, all_nodes)。

    root_nodes 是顶层元素的列表；all_nodes 按文档顺序包含所有元素。
    """
    n = len(src)
    i = 0
    root: list[Node] = []
    all_nodes: list[Node] = []
    stack: list[Node] = []

    def current():
        return stack[-1] if stack else None

    while i < n:
        lt = src.find("<", i)
        if lt == -1:
            cur = current()
            if cur is not None:
                cur.texts.append((i, n))
            break
        if lt > i:
            cur = current()
            if cur is not None:
                cur.texts.append((i, lt))
            i = lt

        if src.startswith("<!--", i):
            e = src.find("-->", i)
            i = n if e == -1 else e + 3
            continue
        if src.startswith("<!", i) or src.startswith("<?", i):
            e = src.find(">", i)
            i = n if e == -1 else e + 1
            continue

        is_end = src.startswith("</", i)
        tag_end = _find_tag_end(src, i)
        m = _TAG_NAME.match(src, i)
        name = m.group(1).lower() if m else ""
        tag_src = src[i:tag_end]

        if is_end:
            for k in range(len(stack) - 1, -1, -1):
                if stack[k].name == name:
                    for node in stack[k:]:
                        node.content_end = i
                    del stack[k:]
                    break
            i = tag_end
            continue

        # 开启标签
        node = Node(name, i, tag_end, tag_src, current())
        all_nodes.append(node)
        if current() is not None:
            current().children.append(node)
        else:
            root.append(node)

        if name in RAW_TAGS:
            # script/style 的内容原样跳过，直接找结束标签
            close = src.find("</" + name, tag_end)
            if close == -1:
                node.content_start = tag_end
                node.content_end = n
                i = n
            else:
                node.content_start = tag_end
                node.content_end = close
                i = close
            continue

        if name not in VOID_TAGS and not tag_src.rstrip().endswith("/>"):
            stack.append(node)
        i = tag_end

    for node in stack:
        node.content_end = n
    return root, all_nodes
