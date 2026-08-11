"""Scanner configuration: canonical categories, sources, and politeness settings."""

from dataclasses import dataclass, field
from pathlib import Path

# Canonical 10 categories — must match the catalog exactly.
CANONICAL_CATEGORIES = [
    "Aircraft",
    "UAVs",
    "Air-launched munitions",
    "Rocket and missile weapons",
    "Sea-launched cruise missiles",
    "EW assets",
    "UGVs",
    "Armored vehicles and equipment",
    "Automotive vehicles",
    "Small arms",
]

# Canonical key -> display name
CATEGORY_KEYS = {
    "aircraft": "Aircraft",
    "uavs": "UAVs",
    "air-launched-munitions": "Air-launched munitions",
    "rocket-and-missile-weapons": "Rocket and missile weapons",
    "sea-launched-cruise-missiles": "Sea-launched cruise missiles",
    "ew-assets": "EW assets",
    "ugvs": "UGVs",
    "armored-vehicles-and-equipment": "Armored vehicles and equipment",
    "automotive-vehicles": "Automotive vehicles",
    "small-arms": "Small arms",
}
KEY_TO_CATEGORY = CATEGORY_KEYS


def category_key(display: str) -> str:
    for k, v in CATEGORY_KEYS.items():
        if v.lower() == display.lower():
            return k
    raise KeyError(f"unknown category: {display}")


# Category classifier: ordered keyword rules against the product path.
# Order matters — more specific rules first (e.g. SLCM before generic missiles).
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("sea-launched-cruise-missiles", ["navy/weapons-systems/missiles", "anti-ship", "cruise-missiles", "naval-strike"]),
    ("air-launched-munitions", ["air-launched", "air-to-air-missile", "air-to-ground", "smart-bombs", "precision-guided", "bombs", "smart-munition"]),
    ("uavs", ["unmanned-aerial-vehicles", "unmanned-aerial-system", "loitering", "kamikaze", "uav", "drones"]),
    ("ugvs", ["unmanned-ground-vehicles", "ugv", "unmanned-ground"]),
    ("ew-assets", ["electronic-warfare", "jammer", "electronic-countermeasure", "signal-intelligence", "reconnaissance-systems"]),
    ("rocket-and-missile-weapons", ["ballistic-missiles", "tactical-missiles", "air-defense", "missiles", "rockets", "artillery-vehicles-and-weapons"]),
    ("armored-vehicles-and-equipment", ["main-battle-tanks", "infantry-fighting-vehicles", "armoured-personnel", "armored-personnel",
                                        "armoured-vehicles", "armored-vehicles", "tank-destroyer", "fire-support-vehicles",
                                        "self-propelled", "tanks", "mrap", "ambulance", "command-post"]),
    ("automotive-vehicles", ["logistic-trucks", "tactical-and-logistic-vehicles", "trucks", "cargo", "logistic", "automotive", "light-tactical"]),
    ("aircraft", ["air/fighter", "air/attack", "air/bomber", "air/transport", "air/utility", "air/rotary", "air/helicopter", "helicopter", "air/"]),
    ("small-arms", ["weapons/assault-rifles", "weapons/machine-guns", "weapons/pistols", "weapons/sniper", "weapons/", "small-arms", "rifles"]),
]


def classify_path(path: str) -> str | None:
    """Classify a /military-products/... sub-path into a category key."""
    p = path.lower()
    for key, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in p:
                return key
    return None


def rule_index_for_path(path: str) -> int | None:
    """Index of the first matching rule (0 = most specific). None if unmapped.

    Used by the curator to score category confidence: the earlier a rule matched
    the more specific it is, so earlier = more confident."""
    p = path.lower()
    for i, (_key, kws) in enumerate(CATEGORY_RULES):
        for kw in kws:
            if kw in p:
                return i
    return None


@dataclass
class Settings:
    """Runtime settings. Everything overridable via CLI flags / env vars."""

    # Politeness & load
    min_delay_seconds: float = 1.5          # minimum gap between requests to the SAME host
    max_workers: int = 1                    # per-host concurrency is always 1 (politeness);
                                            # this is total workers across hosts
    request_timeout: float = 30.0
    max_retries: int = 3
    backoff_base: float = 2.0
    user_agent: str = "ASAN-Scanner/1.0 (+A-SAN research catalog; ops@asan.local)"
    obey_robots: bool = True                # NEVER set False unless site ops explicitly whitelists
                                            # the scanner UA — see POLICY.md. Default True, hard rule.
    use_cache: bool = True
    refresh: bool = False                   # re-fetch even if cached

    # Scope
    categories: list[str] = field(default_factory=lambda: [v for _, v in CATEGORY_KEYS.items()])
    limit: int | None = None                # cap number of product pages fetched this run
    max_page_size_kb: int = 2048            # cap on stored raw HTML per page

    # Paths
    root: Path = Path(__file__).resolve().parent.parent
    db_path: Path = Path("data/scan.db")
    cache_dir: Path = Path("data/cache")    # optional disk mirror of raw HTML
    catalog_path: Path = Path("catalog-data.json")  # absolute-ised in cli
    seeds_path: Path = Path("seeds/categories.json")

    # Official API credentials (env) — only used if set. Never stored.
    espacenet_ops_key: str = ""
    espacenet_ops_secret: str = ""

    def __post_init__(self):
        if not self.root.is_absolute():
            self.root = Path.cwd()
        self.db_path = self._abs(self.db_path)
        self.cache_dir = self._abs(self.cache_dir)
        self.catalog_path = self._abs(self.catalog_path)
        self.seeds_path = self._abs(self.seeds_path)

    def _abs(self, p: Path) -> Path:
        return p if p.is_absolute() else (self.root / p)

    @property
    def domains(self):
        return {"www.armyrecognition.com", "patents.google.com",
                "worldwide.espacenet.com", "ppubs.uspto.gov", "janes.com"}
