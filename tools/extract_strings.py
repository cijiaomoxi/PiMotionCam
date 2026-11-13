#!/usr/bin/env python3
"""提取 index.html / login.html / app.js 里所有面向用户的中文文案，供建 i18n key 表。"""
import io
import re
import sys

TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)>([^<]*)</\1>", re.S)


def html_strings(path):
    s = io.open(path, encoding="utf-8").read()
    # 去掉 <script> / <style> / 注释的内容，它们不是面向用户的文案
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    out = []
    # 1) 带文本的元素
    for m in TAG_RE.finditer(s):
        tag, attrs, text = m.group(1), m.group(2), m.group(3).strip()
        if not re.search(r"[\u4e00-\u9fff]", text):
            continue
        ident = re.search(r'id="([^"]+)"', attrs)
        out.append(("TEXT", tag, ident.group(1) if ident else "-",
                    " ".join(text.split())))
    # 2) 属性里的中文（title / placeholder / alt / value）
    for m in re.finditer(r'\b(title|placeholder|alt|value)="([^"]*[\u4e00-\u9fff][^"]*)"', s):
        out.append(("ATTR:" + m.group(1), "", "-", m.group(2)))
    return out


def js_strings(path):
    s = io.open(path, encoding="utf-8").read()
    out = []
    # 单引号 / 双引号字符串字面量里的中文
    for m in re.finditer(r"'((?:[^'\\\n]|\\.)*[\u4e00-\u9fff](?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*[\u4e00-\u9fff](?:[^\"\\\n]|\\.)*)\"", s):
        lit = m.group(1) or m.group(2)
        line = s[:m.start()].count("\n") + 1
        out.append((str(line), "", "-", lit))
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "html"):
        for p in ("templates/index.html", "templates/login.html"):
            print("=" * 70)
            print(p)
            print("=" * 70)
            for kind, tag, ident, text in html_strings(p):
                print("%-14s %-8s %-22s %s" % (kind, tag, ident, text))
    if which in ("all", "js"):
        print("=" * 70)
        print("static/app.js")
        print("=" * 70)
        seen = set()
        for line, tag, ident, text in js_strings("static/app.js"):
            if text in seen:
                continue
            seen.add(text)
            print("%-6s %s" % (line, text))
