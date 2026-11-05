"""
OFAC SDN sanctioned-entity lookup.

Source: OpenSanctions us_ofac_sdn dataset (CC-BY 4.0)
The list is cached in-memory and refreshed every 24 hours.
"""

import csv
import io
import time
from typing import List, Optional, Dict, Set
import httpx

SDN_CSV_URL = "https://data.opensanctions.org/datasets/latest/us_ofac_sdn/targets.simple.csv"
TTL_SECONDS = 24 * 60 * 60  # 24 hours


class SanctionEntry:
    def __init__(self, id: str, schema: str, name: str, aliases: List[str], 
                 countries: List[str], programs: List[str], sanctions: str,
                 first_seen: Optional[str] = None, last_seen: Optional[str] = None):
        self.id = id
        self.schema = schema
        self.name = name
        self.aliases = aliases
        self.countries = countries
        self.programs = programs
        self.sanctions = sanctions
        self.first_seen = first_seen
        self.last_seen = last_seen

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "schema": self.schema,
            "name": self.name,
            "aliases": self.aliases,
            "countries": self.countries,
            "programs": self.programs,
            "sanctions": self.sanctions,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class SanctionsCache:
    def __init__(self):
        self.entries: List[SanctionEntry] = []
        self.by_norm_name: Dict[str, List[SanctionEntry]] = {}
        self.fetched_at: float = 0
        self._loading = False

    def _normalize(self, s: str) -> str:
        """Lower-case, strip punctuation, collapse whitespace."""
        import re
        s = s.lower()
        s = re.sub(r'[^\w\s]', ' ', s, flags=re.UNICODE)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    async def load(self) -> None:
        """Load the SDN list from OpenSanctions."""
        if self._loading:
            return
        if self.entries and (time.time() - self.fetched_at) < TTL_SECONDS:
            return

        self._loading = True
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(SDN_CSV_URL)
                response.raise_for_status()
                text = response.text

            reader = csv.DictReader(io.StringIO(text))
            entries = []
            by_norm_name: Dict[str, List[SanctionEntry]] = {}

            for row in reader:
                if not row.get('name'):
                    continue

                entry = SanctionEntry(
                    id=row.get('id', ''),
                    schema=row.get('schema', 'LegalEntity'),
                    name=row['name'],
                    aliases=[a.strip() for a in row.get('aliases', '').split(';') if a.strip()],
                    countries=[c.strip() for c in row.get('countries', '').split(';') if c.strip()],
                    programs=[p.strip() for p in row.get('program_ids', '').split(';') if p.strip()],
                    sanctions=row.get('sanctions', ''),
                    first_seen=row.get('first_seen'),
                    last_seen=row.get('last_seen'),
                )
                entries.append(entry)

                # Index by normalized name and aliases
                keys = set([self._normalize(entry.name)] + 
                          [self._normalize(a) for a in entry.aliases])
                for key in keys:
                    if key:
                        if key not in by_norm_name:
                            by_norm_name[key] = []
                        by_norm_name[key].append(entry)

            self.entries = entries
            self.by_norm_name = by_norm_name
            self.fetched_at = time.time()

        except Exception as e:
            # If we have old data, keep using it
            if not self.entries:
                raise
            print(f"Warning: Failed to refresh sanctions list: {e}")
        finally:
            self._loading = False

    async def match_exact(self, query: str) -> List[SanctionEntry]:
        """Exact match lookup."""
        if not query or len(query) < 3:
            return []
        await self.load()
        normalized = self._normalize(query)
        return self.by_norm_name.get(normalized, [])

    async def search(self, query: str, schema: Optional[str] = None, 
                     limit: int = 50) -> List[SanctionEntry]:
        """Substring + contains search."""
        if not query or len(query) < 4:
            return []
        await self.load()
        
        q = self._normalize(query)
        exact_name = []
        exact_alias = []
        sub_name = []
        sub_alias = []
        seen: Set[str] = set()

        def push(bucket: List[SanctionEntry], e: SanctionEntry):
            if e.id in seen:
                return
            if schema and e.schema != schema:
                return
            seen.add(e.id)
            bucket.append(e)

        for entry in self.entries:
            name_norm = self._normalize(entry.name)
            if name_norm == q:
                push(exact_name, entry)
            elif any(self._normalize(a) == q for a in entry.aliases):
                push(exact_alias, entry)
            elif q in name_norm:
                push(sub_name, entry)
            elif any(q in self._normalize(a) for a in entry.aliases):
                push(sub_alias, entry)
            if len(seen) >= limit * 4:
                break

        return (exact_name + exact_alias + sub_name + sub_alias)[:limit]

    async def index_size(self) -> int:
        await self.load()
        return len(self.entries)


# Global cache instance
sanctions_cache = SanctionsCache()
