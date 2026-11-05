#!/usr/bin/env python3
path = "/tmp/cdp/repel.js"
src = open(path).read()
old = "document.getElementById('graph-repel; el.dispatchEvent"
new = "document.getElementById('graph-repel'); el.value='20'; el.dispatchEvent"
assert old in src, "not found"
src = src.replace(old, new)
open(path, "w").write(src)
print("fixed")