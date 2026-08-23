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
    "Naval vessels",
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
    "naval-vessels": "Naval vessels",
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
    ("naval-vessels", ["navy/aircraft-carriers", "navy/frigates", "navy/submarines", "navy/corvettes",
                       "navy/destroyers-cruisers", "navy/amphibious-warfare-ship", "navy/patrol-vessels",
                       "navy/minehunter", "navy/auxiliary-ships", "navy/naval-aircraft",
                       "navy/rigid-inflatable-boat", "navy/naval-combat-equipment", "navy/unmanned-systems"]),
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


# ---------- News-article classifier ----------
# Army Recognition news titles are free text (no stable URL path taxonomy), so we
# classify by keyword presence in the title/body. Order = specificity.
ARTICLE_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("sea-launched-cruise-missiles", ["cruise missile", "slcm", "naval strike", "anti-ship missile"]),
    ("naval-vessels", ["frigate", "destroyer", "corvette", "submarine", "aircraft carrier",
                       "amphibious assault", "patrol vessel", "mine hunter", "warship"]),
    ("air-launched-munitions", ["jdam", "jdam", "bomb", "guided bomb", "air-to-air missile",
                                "air-to-surface", "precision-guided", "cruise missile air"]),
    ("rocket-and-missile-weapons", ["ballistic missile", "icbm", "irbm", "medium-range ballistic",
                                    "short-range ballistic", "anti-tank missile", "atgm", "mlrs",
                                    "multiple launch rocket", "scud", "is kander", "patriot", "s-400",
                                    "himars", "tomahawk", "atacms", "fateh", "recoilless",
                                    "shoulder-fired", "grenade launcher", "man-portable",
                                    "anti-tank weapon"]),
    ("aircraft", ["fighter", "f-35", "f-16", "rafale", "su-57", "eurofighter", "f-22", "f-15",
                  "f-14", "f-18", "f-20", "fj-31", "j-20", "j-31", "typhoon", "gripen", "hornets",
                  "super hornet", "harrier", "a10", "a-10", "transport aircraft", "tanker",
                  "aerial refueling", "awacs", "early warning"]),
    ("uavs", ["uav", "uas", "drone", "loitering", "kamikaze", "mq-", "bayraktar", "shahed",
              "switchblade", "wing loong", "predator", "reaper"]),
    ("ew-assets", ["radar", "electronic warfare", "jammer", "signals intelligence", "sigint",
                   "electronic countermeasure", "ecm", "giraffe", "surveillance radar",
                   "air defense radar", "phased array"]),
    ("ugvs", ["ugv", "unmanned ground vehicle", "robotic ground", "ground robot"]),
    ("armored-vehicles-and-equipment", ["tank", "mbt", "main battle tank", "ifv", "infantry fighting vehicle",
                                        "apc", "armored personnel carrier", "armoured", "mrap", "afv",
                                        "self-propelled", "howitzer", "artillery system", "spg"]),
    ("automotive-vehicles", ["truck", "logistics vehicle", "tactical truck", "cargo truck", "transport vehicle"]),
    ("small-arms", ["rifle", "pistol", "machine gun", "assault rifle", "sniper", "light machine gun",
                    "submachine gun", "handgun", "automatic rifle"]),
]


def classify_article(text: str) -> str | None:
    """Classify a news article (title+body) -> category key, by keyword priority."""
    p = (text or "").lower()
    for key, kws in ARTICLE_CATEGORY_RULES:
        for kw in kws:
            if kw in p:
                return key
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
    catalog_path: Path = Path("../catalog-data.json")  # scanner lives inside a-san/
    seeds_path: Path = Path("seeds/categories.json")

    # Official API credentials (env) — only used if set. Never stored.
    espacenet_ops_key: str = ""
    espacenet_ops_secret: str = ""
    uspto_odp_token: str = ""   # USPTO Open Data Portal bearer token (data.uspto.gov)

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
                "worldwide.espacenet.com", "ppubs.uspto.gov", "janes.com",
                "www.militaryfactory.com",
                "www.designation-systems.net", "missilethreat.csis.org",
                "modernfirearms.net", "milremrobotics.com", "man.fas.org",
                "en.wikipedia.org",
                "war-sanctions.gur.gov.ua", "en.defence-ua.com",
                "defence-ua.com", "baykartech.com", "army-guide.com",
                "www.globalsecurity.org", "www.hisutton.com",
                "www.seaforces.org"}
