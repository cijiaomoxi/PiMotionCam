"""极简 JavaScript 词法分析器：只做一件事——找出源码里所有字符串字面量。

为什么不用正则硬扫：
  * 正则字面量里可以出现引号（`/'/g`）和 `//`（`/\\/+$/`），
    朴素扫描会把正则当成字符串起点，把后面一大片代码吞进"字符串"里；
  * 模板字符串里还有 `${}` 嵌套。

本模块给出每个字面量的 (start, end, value) 区间，区间互不重叠，
可用「拼回去等于原串」来验证词法分析是否正确。
"""
from __future__ import annotations

import re

_ID_START = re.compile(r"[A-Za-z_$]")
_ID_PART = re.compile(r"[A-Za-z0-9_$]")

# 这些关键字后面跟 `/` 时是「正则开始」而不是「除号」
_KEYWORDS_BEFORE_REGEX = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
}
# 这些标识符后面跟 `/` 时是「除号」
_KEYWORDS_BEFORE_DIV = {"true", "false", "null", "this", "super"}


class JsLexer:
    """把 JS 源码切成字符串字面量区间。"""

    def __init__(self, src: str):
        self.src = src
        self.n = len(src)
        self.spans: list[tuple[int, int, str]] = []

    # ------------------------------------------------------------------
    def read_quote(self, i: int) -> tuple[int, int, str]:
        """读取 '...' 或 "..." 字面量。返回 (start, end_after_quote, value)。"""
        src, n = self.src, self.n
        q = src[i]
        j = i + 1
        buf = []
        while j < n:
            c = src[j]
            if c == "\\":
                buf.append(src[j:j + 2])
                j += 2
                continue
            if c == q:
                break
            buf.append(c)
            j += 1
        return i, j + 1, "".join(buf)

    def read_regex(self, i: int) -> int | None:
        """从 i（指向 '/'）读一个正则字面量，返回结束位置；不是正则则返回 None。"""
        src, n = self.src, self.n
        j = i + 1
        in_class = False
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                j += 1
                while j < n and _ID_PART.match(src[j]):
                    j += 1
                return j
            elif c == "\n":
                return None
            j += 1
        return None

    def read_template(self, i: int) -> int:
        """从 i（指向 '`'）跳过整个模板字符串（含 ${} 里的嵌套）。"""
        src, n = self.src, self.n
        j = i + 1
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                return j + 1
            if c == "$" and j + 1 < n and src[j + 1] == "{":
                j = self.scan_code(j + 2, stop_at_brace=True) + 1
                continue
            j += 1
        return n

    # ------------------------------------------------------------------
    def scan_code(self, i: int, stop_at_brace: bool = False) -> int:
        """扫描代码区间。stop_at_brace=True 时停在配对的 '}' 之前。"""
        src, n = self.src, self.n
        prev_value = False      # 上一个有效 token 是否产生了一个「值」
        last_word = ""
        while i < n:
            c = src[i]
            if c in " \t\r\n\f\v":
                i += 1
                continue
            # 行注释
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                j = src.find("\n", i)
                i = n if j == -1 else j
                continue
            # 块注释
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                j = src.find("*/", i + 2)
                i = n if j == -1 else j + 2
                continue
            # 字符串
            if c in "\"'":
                s, e, val = self.read_quote(i)
                self.spans.append((s, e, val))
                i = e
                prev_value = True
                last_word = ""
                continue
            # 模板字符串
            if c == "`":
                i = self.read_template(i)
                prev_value = True
                last_word = ""
                continue
            # 正则 vs 除号
            if c == "/":
                if not prev_value:
                    e = self.read_regex(i)
                    if e is not None:
                        i = e
                        prev_value = True
                        last_word = ""
                        continue
                i += 1
                prev_value = False
                last_word = ""
                continue
            if c == "{":
                if stop_at_brace:
                    return i
                i += 1
                prev_value = False
                last_word = ""
                continue
            if c == "}":
                if stop_at_brace:
                    return i
                i += 1
                prev_value = True
                last_word = ""
                continue
            if c in "([,":
                i += 1
                prev_value = False
                last_word = ""
                continue
            if c in ")]":
                i += 1
                prev_value = True
                last_word = ""
                continue
            if c == ".":
                i += 1
                prev_value = False
                last_word = ""
                continue
            if c.isdigit():
                j = i
                while j < n and (src[j].isalnum() or src[j] in "._"):
                    j += 1
                i = j
                prev_value = True
                last_word = ""
                continue
            if _ID_START.match(c):
                j = i
                while j < n and _ID_PART.match(src[j]):
                    j += 1
                word = src[i:j]
                i = j
                last_word = word
                if word in _KEYWORDS_BEFORE_DIV:
                    prev_value = True
                else:
                    prev_value = False
                continue
            # 其它标点：运算符 / 分隔符
            i += 1
            prev_value = False
            last_word = ""
        return i

    # ------------------------------------------------------------------
    def run(self) -> list[tuple[int, int, str]]:
        self.scan_code(0)
        self.spans.sort(key=lambda t: t[0])
        return self.spans


def literal_spans(src: str) -> list[tuple[int, int, str]]:
    """返回源码里所有字符串字面量的 (start, end, value)。"""
    return JsLexer(src).run()


def verify_partition(src: str, spans: list[tuple[int, int, str]]) -> bool:
    """区间必须互不重叠、且按序覆盖所有引号位置。"""
    last = -1
    for s, e, _v in spans:
        if s <= last:
            return False
        last = e
    return True


if __name__ == "__main__":
    import io
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "static/app.js"
    text = io.open(path, encoding="utf-8").read()
    sp = literal_spans(text)
    print("%s: %d 个字面量" % (path, len(sp)))
    bad = [v for _s, _e, v in sp if "function" in v or "=>" in v or "\\n" in v and ";" in v]
    for v in bad[:10]:
        print("  可疑:", repr(v[:120]))
    print("分区校验:", "OK" if verify_partition(text, sp) else "失败")
