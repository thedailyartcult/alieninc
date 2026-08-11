"""Tolerant HTML parsing using only the stdlib.

Supports the two markup styles seen in the wild on the target sites:
1. UIkit-style definition lists: <li class="el-item"><div class="el-title">Label</div>
   <div class="el-content">Value (may contain nested <ul>/<li>)</div></li>
2. Classic <table><tr><th>Label</th><td>Value</td></tr>...
Plus generic title / paragraph extraction and Google Patents meta extraction.
"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)          # &#39; &amp; &nbsp; &lt; &gt; entities -> chars
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ,", ",").replace(" .", ".")
    return s.strip()


def extract_title(html: str) -> str:
    """Canonical title: first <title> tag wins (pages have stray unclosed
    <title>/<h1> deep in the body that corrupt stateful parsing)."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S)
    if m:
        t = clean_text(m.group(1))
        if t:
            return _strip_site_suffix(t)
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html or "", re.S)
    for h in h1s:
        t = clean_text(h)
        if t:
            return _strip_site_suffix(t)
    return ""


def _strip_site_suffix(t: str) -> str:
    for marker in ("Army Recognition", " - Military", " | Military", "Wikipedia", " - Wikipedia"):
        if marker.lower() in t.lower():
            head = t.split(marker, 1)[0].rstrip(" -|–—:·.")
            if head.strip():
                return head.strip()
    return t.strip(" .·")


def _classes(attrs) -> list[str]:
    out = []
    for k, v in attrs:
        if k == "class" and v:
            out.extend(v.split())
    return out


class _Collector(HTMLParser):
    """Collects title, paragraphs, el-item pairs and table rows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title: str = ""
        self.paragraphs: list[str] = []
        self.items: list[tuple[str, str]] = []      # label, value
        self.table_rows: list[tuple[str, str]] = [] # label, value

        self._in_title = 0
        self._in_h1 = 0
        self._p_buf: list[str] = []
        self._in_p = 0

        # el-item state
        self._li_depth = 0
        self._in_el_item = False
        self._label: list[str] = []
        self._value: list[str] = []
        self._in_label = False
        self._in_value = False

        # table state
        self._in_th = False
        self._in_td = False
        self._th_buf: list[str] = []
        self._td_buf: list[str] = []
        self._tr_depth = 0
        self._row_tds: list[str] = []
        self._row_th_seen = False
        self._td_is_label = False
        self._pending_label: str | None = None

    def handle_starttag(self, tag, attrs):
        classes = _classes(attrs)
        if tag == "title":
            self._in_title += 1
        elif tag == "h1" and not self.title:
            self._in_h1 += 1
        elif tag == "p":
            self._in_p += 1
        elif tag == "li":
            self._li_depth += 1
            if self._li_depth == 1 and "el-item" in classes:
                self._in_el_item = True
                self._label, self._value = [], []
        elif tag == "div":
            if self._in_el_item:
                if "el-title" in classes:
                    self._in_label = True
                elif "el-content" in classes:
                    self._in_value = True
        elif tag == "th":
            self._in_th = True
            self._th_buf = []
            self._row_th_seen = True
        elif tag == "td":
            self._in_td = True
            self._td_buf = []
            self._td_is_label = False
        elif tag == "tr":
            self._tr_depth += 1
            self._row_tds = []
            self._row_th_seen = False
        elif tag == "strong":
            if self._in_td:
                self._td_is_label = True
    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title -= 1
        elif tag == "h1":
            self._in_h1 -= 1
        elif tag == "p":
            if self._in_p > 0:
                self._in_p -= 1
            txt = clean_text("".join(self._p_buf))
            if txt:
                self.paragraphs.append(txt)
            self._p_buf = []
        elif tag == "li":
            self._li_depth -= 1
            if self._li_depth <= 0 and self._in_el_item:
                label = " ".join("".join(self._label).split())
                value = clean_text("".join(self._value))
                if label and value:
                    self.items.append((label, value))
                self._in_el_item = False
                self._in_label = False
                self._in_value = False
        elif tag == "div":
            if self._in_label:
                self._in_label = False
            elif self._in_value:
                self._in_value = False
        elif tag == "th":
            self._in_th = False
            self._th_buf = []
        elif tag == "td":
            if self._in_td:
                self._in_td = False
                cell = clean_text("".join(self._td_buf))
                if cell:
                    self._row_tds.append(cell)
                    if self._td_is_label:
                        self._pending_label = cell
                    elif self._pending_label:
                        # grid layout: label row, then value row
                        self.table_rows.append((self._pending_label, cell))
                        self._pending_label = None
                if self._th_buf and self._td_buf:
                    self.table_rows.append((clean_text("".join(self._th_buf)),
                                            clean_text("".join(self._td_buf))))
                self._th_buf, self._td_buf = [], []
        elif tag == "tr":
            # Emit on every </tr> — messy/nested table HTML on these sites
            # unbalances tr-depth, so we don't gate on it.
            if len(self._row_tds) >= 2 and not self._row_th_seen:
                # td-pair markup (label / value), no <th>
                self.table_rows.append((self._row_tds[0],
                                        " ".join(self._row_tds[1:])))
            self._row_tds = []

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + data).strip()
        if self._in_h1:
            self.title = (self.title + " " + data).strip()
        if self._in_p:
            self._p_buf.append(data)
        if self._in_el_item:
            if self._in_label:
                self._label.append(data)
            if self._in_value:
                self._value.append(data)
        if self._in_th:
            self._th_buf.append(data)
        if self._in_td:
            self._td_buf.append(data)


def parse_html(html: str) -> dict:
    c = _Collector()
    try:
        c.feed(html or "")
        c.close()
    except Exception:
        pass
    items = list(c.items)
    if not items:
        items = list(c.table_rows)
    # dedupe identical label:value
    seen, out = set(), []
    for label, value in items:
        key = (label.strip().lower(), value[:60].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((label.strip(), value.strip()))
    desc = ""
    for p in c.paragraphs:
        if len(p) > 80:
            desc = p
            break
    if not desc and c.paragraphs:
        desc = c.paragraphs[0]
    title = extract_title(html)
    if not title:
        title = clean_text(c.title)[:200]
    return {"title": title, "description": desc,
            "specs": out, "paragraphs": c.paragraphs}


# ---------- Google Patents ----------
_PUB_RE = re.compile(r"(?i)((?:US|EP|WO|CN|JP|KR|DE|FR|GB)\d{5,})")


def parse_google_patents(html: str) -> dict:
    meta = {}
    for m in re.finditer(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"', html):
        meta[m.group(1).lower()] = m.group(2)
    title_m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = clean_text(title_m.group(1)) if title_m else ""
    pubs = _PUB_RE.findall(title)
    pub = pubs[0] if pubs else ""
    abstract = meta.get("description", "")
    if not abstract:
        am = re.search(r'itemprop="description"\s+content="([^"]+)"', html)
        abstract = clean_text(am.group(1)) if am else ""
    return {"title": title, "publication": pub, "abstract": abstract,
            "meta": {k: v for k, v in list(meta.items())[:12]}}
