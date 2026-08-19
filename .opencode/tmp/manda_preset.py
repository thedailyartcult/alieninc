#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()
old = "    manda: { label: 'Manda', repel: 0, link: 0, gravity: 0, font: 12, size: 3, linkw: 0.6, labelDensity: 24, curve: 0, particles: 0 },"
new = "    manda: { label: 'Manda', repel: 48, link: 16, gravity: 48, font: 12, size: 3, linkw: 0.6, labelDensity: 24, curve: 0, particles: 0 },"
assert src.count(old) == 1, f"count {src.count(old)}"
src = src.replace(old, new)
open(path, "w").write(src)
print("manda preset defaults fixed")
