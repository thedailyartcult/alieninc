#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

bad1 = "node.mandaSide = (ci % 2 === 0) ? in : out;"
good1 = "node.mandaSide = (ci % 2 === 0) ? 'in' : 'out';"
assert src.count(bad1) == 1, f"bad1 count {src.count(bad1)}"
src = src.replace(bad1, good1)

bad2 = "node.mandaLabel = C + (ci + 1) + . + (i + 1);"
good2 = "node.mandaLabel = 'C' + (ci + 1) + '.' + (i + 1);"
assert src.count(bad2) == 1, f"bad2 count {src.count(bad2)}"
src = src.replace(bad2, good2)

open(path, "w").write(src)
print("fixed OK")
