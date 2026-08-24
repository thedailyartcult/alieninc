"""Designation sanity gate.

`looks_like_news_headline()` classifies catalog designations that are really
news-article/blog titles scraped from news-style feeds (Defense Express,
Covert Shores, Army Recognition articles) rather than equipment names. The
scanner refuses to upsert such rows and `purge_headlines.py` removes existing
ones, so Panteon's ontology never materializes headlines as weapon systems.

Tuning contract (validated against the live catalog):
- catches ~80% of Defense Express titles and Covert Shores blog posts
- ZERO false positives on reference sources (MilitaryFactory, Weaponsystems,
  Seaforces, Army Guide, Designation-Systems, ModernFirearms)
"""
import re

_STOP = set(
    "the a an its his her their of for by with from in on at to and or as is "
    "are was were be been being that this these those it he she they we you i "
    "not no than then more most over under into out up down about after before "
    "between during".split())

_STRONG = re.compile(
    r"\b(says?|said|amid|shot ?down|shoots? down|shooting down|downed|unveils|"
    r"unveiled|confirms?|confirmed|reveals?|revealed|report(s|ed|edly)?|"
    r"takes? flight|first time|in history|could |set to|russia'?s|china'?s|"
    r"ukraine'?s|new rival|weekly review|really |secretly |deliberately |"
    r"t-shirts?|in the store)\b", re.I)

_JVERB = re.compile(
    r"\b(needs?|considers?|secures?|becomes?|became|remains?|pays?|backs?|"
    r"builds?|keeps?|gets?|got|chooses?|chose|wants?|seeks?|aims?|faces?|"
    r"fears?|warns?|urges?|plans?|planning|orders?|crashes?|claims?|names?|"
    r"proves?|moves?|priced|bringing|deployed|deploys?)\b", re.I)

_STARTER = re.compile(
    r"^(after|if|how|why|what|did|does|is|are|will|can|could|should|despite|"
    r"amid|with|as|only|who|another|analysis|artwork|gallery|update|news|more|list)\b",
    re.I)

_NUM_ADJ = re.compile(r"^\d{1,2}\s+(new|rare|more|unexplained|chinese|russian|american)\b", re.I)

_POSS = re.compile(r"(?:'s|\u2019s)\s")


def looks_like_news_headline(text: str) -> bool:
    """True when the string reads like an article headline, not a system name."""
    t = (text or "").replace("\u200b", "").strip()
    if not t:
        return False
    words = t.split()
    n = len(words)
    stop_ratio = sum(
        1 for w in words
        if w.lower().strip('.,!?:"\'\u2014\u2013-') in _STOP) / max(n, 1)
    if "?" in t:
        return True
    if _STRONG.search(t) and n >= 5:
        return True
    if _STARTER.match(t) and n >= 6:
        return True
    if _NUM_ADJ.match(t) and n >= 4:
        return True
    if _POSS.search(t) and n >= 8:
        return True
    # comma splice: ", Capitalized ..." plus sentence-length
    if len(re.findall(r",\s+[A-Z]", t)) >= 1 and n >= 9 and stop_ratio >= 0.18:
        return True
    if _JVERB.search(t) and n >= 7:
        return True
    if n >= 10 and stop_ratio >= 0.32:
        return True
    if re.search(r"[.!?]$", t) and n >= 6 and stop_ratio >= 0.25:
        return True
    return False
