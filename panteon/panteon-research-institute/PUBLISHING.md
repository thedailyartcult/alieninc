# Publishing to the Panteon Research Institute

The publisher is the source of truth for PRI articles and the archive index. Do not edit `index.html`, `locked.html`, or files in `articles/` by hand.

## 1. Organize source by year

Place each Markdown document in the directory for its publication year:

```text
source/
  2016/
    founding-charter.md
  2026/
    measuring-ai-capability.md
```

Use a dated front-matter document for historical work. This keeps the year folder, the article date, and the archive index aligned.

```md
---
title: Your Article Title
tag: Panteon Research Institute
topic: AI Capability
date: 2026-08-02
author: Patrick Neil A.
slug: your-article-title
---

# First section
```

`topic` controls the **Articles by Topic** grouping. Use a deliberate, consistent topic name; it is displayed in the archive index.

Bare Markdown remains supported for new work. Its first `#` is the title, but it defaults to today’s date and the institute topic, so use front matter for any article that needs a specific historic date or topic. You may omit `title` from front matter and keep the first `#` as the title while still supplying `date` and `topic`.

## 2. Publish

```bash
python3 publish.py
python3 publish.py 2026/your-article.md
```

The publisher recursively reads every `source/**/*.md` file. It rebuilds the landing page, protected archive records, and the locked-document screen each time.

## Access model

PRI records dated on or after 2016-12-22 are restricted automatically. The landing page may show their title, date, author, and topic for navigation; the article body is written only to the private archive store and opens through authenticated access.

The date archive intentionally exposes August as its monthly browsing surface. The topic index always includes all published metadata.
