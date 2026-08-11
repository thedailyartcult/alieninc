"""A-SAN deep scanner: robots-compliant, resumable, category-aware catalog crawler.

The scanner enumerates the allowed product trees of the approved public sources
(Army Recognition /military-products, Google Patents, and — with official
credentials — Espacenet OPS and USPTO), fetches full pages, parses the public
spec content, de-duplicates, and merges into the A-SAN catalog schema.

Design rules (religious):
- robots.txt is ALWAYS honoured (never bypassed). Only paths the site allows
  for the scanner user-agent are fetched.
- Data is only ever what is printed on the fetched page. Nothing invented.
- Every entry keeps exact source URL(s) + fetched_at as provenance.
- Runs are resumable, cached, de-duplicated and polite by default.
"""

__version__ = "1.0.0"
