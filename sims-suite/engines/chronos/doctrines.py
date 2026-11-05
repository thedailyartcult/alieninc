"""Chronos doctrine registry — historically grounded, cited, per-nation.

Why this exists: the user contract for Chronos is "religious about details,
not guesses". CDB90 already carries per-battle quality ratings (leadership,
training, morale, logistics, tech — Dupuy's historical assessments), but
DOCTRINE — the published and practiced method of each army in a given
period — was not modeled. This module adds it as explicit data.

Each profile encodes how an army's actual WWII-era doctrine shaped combat:
  tempo            operational maneuver speed / initiative (Bewegungskrieg,
                   deep operations) vs methodical linear advance
  combined_arms    integration of armor / air / artillery / infantry
  flexibility      junior-leader initiative under disruption (Auftragstaktik
                   vs post-purge Soviet command rigidity)
  set_piece        deliberate prepared-attack methodology (artillery-centric)
  logistic_reach   sustaining combat away from the railhead over days
  defense_doctrine quality of defensive method (elastic defence, fortified
                   zones, motti)

All values are NEUTRAL at 1.0; >1 is doctrinal strength, <1 weakness.
Unknown actors resolve to the generic contemporary profile (all 1.0).

Effects (see engine.side_combat_power):
  attacker power *= tempo scaled by terrain openness (maneuver needs room)
                 *= 1 + (combined_arms - 1) * 0.6
                 *= 1 + (set_piece - 1) * prep_fraction(duration/24h cap)
                 *= 1 + (logistic_reach - 1) * extra_days_beyond_24h/72
  defender power *= defense_doctrine
                 *= 1 + (combined_arms - 1) * 0.4
  surprise damping: defender flexibility stretches/damps the attacker's
  opening-blow ramp; attacker flexibility dampens being surprised itself.
"""

from __future__ import annotations

from dataclasses import dataclass

OPEN_TERRAIN = {"flat", "desert", "rolling", "dunes", "bare", "mixed"}


@dataclass(frozen=True)
class DoctrineProfile:
    key: str
    name: str
    actor: str
    year_from: int
    year_to: int
    tempo: float = 1.0
    combined_arms: float = 1.0
    flexibility: float = 1.0
    set_piece: float = 1.0
    logistic_reach: float = 1.0
    defense_doctrine: float = 1.0
    summary: str = ""
    sources: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "actor": self.actor,
            "tempo": self.tempo,
            "combined_arms": self.combined_arms,
            "flexibility": self.flexibility,
            "set_piece": self.set_piece,
            "logistic_reach": self.logistic_reach,
            "defense_doctrine": self.defense_doctrine,
            "summary": self.summary,
            "sources": list(self.sources),
        }


# --- Nation timelines ------------------------------------------------------
# Period boundaries follow real doctrinal transitions, not round dates.

_GERMANY = [
    DoctrineProfile(
        key="ger-bewegungskrieg", name="Bewegungskrieg / Auftragstaktik",
        actor="Germany", year_from=1933, year_to=1941,
        tempo=1.18, combined_arms=1.12, flexibility=1.20, set_piece=0.96,
        logistic_reach=0.92, defense_doctrine=1.05,
        summary=("Mission-type orders down to junior leaders "
                 "(Truppenfuehrung HDv 300/2); massed panzer divisions aimed at "
                 "shock and encirclement with Stuka close-air support; bypass "
                 "strongpoints. Weakness: horse-drawn logistics limited reach."),
        sources=(
            "Truppenfuehrung HDv 300/2 (German Army field service regulation, 1933/34)",
            "Corum, The Roots of Blitzkrieg (1992)",
            "Murray & Millett (eds.), Military Effectiveness vol II (1988)",
        ),
    ),
    DoctrineProfile(
        key="ger-attrition-elastic", name="Attritional offence / elastic defence",
        actor="Germany", year_from=1942, year_to=1943,
        tempo=1.08, combined_arms=1.08, flexibility=1.15, set_piece=1.00,
        logistic_reach=0.88, defense_doctrine=1.14,
        summary=("Offensive capability eroding against Allied materiel; on the "
                 "defensive the army codified elastic defence in depth - "
                 "thin forward line, mobile reserves counterattack."),
        sources=(
            "US Army, German Defense Tactics Against Russian Breakthroughs (DA Pam 20-233, 1951)",
            "Glantz, After Stalingrad (2009)",
        ),
    ),
    DoctrineProfile(
        key="ger-defence-depth", name="Verteidigung in der Tiefe",
        actor="Germany", year_from=1944, year_to=1945,
        tempo=0.97, combined_arms=1.02, flexibility=1.12, set_piece=1.00,
        logistic_reach=0.80, defense_doctrine=1.25,
        summary=("Fuel-starved, largely horse-drawn force fighting delaying "
                 "defences; doctrine emphasised depth, reverse slopes, and "
                 "counterattack by mobile reserves - tactically excellent even "
                 "while strategically doomed."),
        sources=(
            "US Army DA Pam 20-233 (1951); Lucas & Schmider (eds.), Defence of the Reich?",
            "Citino, The Wehrmacht Retreats (2012)",
        ),
    ),
]

_USSR = [
    DoctrineProfile(
        key="su-purge-rigidity", name="Post-purge rigidity",
        actor="USSR", year_from=1937, year_to=1941,
        tempo=0.90, combined_arms=0.92, flexibility=0.72, set_piece=0.95,
        logistic_reach=0.90, defense_doctrine=0.98,
        summary=("The Tukhachevsky purges gutted the deep-battle officer corps; "
                 "initiative was punished and orders centralised. PU-36 deep "
                 "operations existed on paper but could not be executed."),
        sources=(
            "PKKA Field Service Regulations PU-36 (1936)",
            "Glantz, Stumbling Colossus (1998)",
            "Blythe, A History of Operational Art (Military Review, 2018)",
        ),
    ),
    DoctrineProfile(
        key="su-standing-defence", name="Standing defence / Not One Step Back",
        actor="USSR", year_from=1941, year_to=1942,
        tempo=0.86, combined_arms=0.94, flexibility=0.75, set_piece=1.02,
        logistic_reach=0.85, defense_doctrine=1.04,
        summary=("Rigid linear defence with massed artillery; offensives were "
                 "frontal and inflexible. Stavka Order No. 227 (July 1942) "
                 "restored spine by coercion rather than skill."),
        sources=(
            "Stavka Order No. 227 (28 July 1942)",
            "Glantz & House, When Titans Clashed (1995)",
        ),
    ),
    DoctrineProfile(
        key="su-deep-battle-maturing", name="Deep battle maturing / maskirovka",
        actor="USSR", year_from=1943, year_to=1943,
        tempo=1.06, combined_arms=1.08, flexibility=0.92, set_piece=1.10,
        logistic_reach=0.98, defense_doctrine=1.10,
        summary=("Post-Stalingrad reconstruction: artillery-centric deliberate "
                 "attacks, systematic maskirovka deception planning, restored "
                 "corps-level maneuver. Still cautious below the operational level."),
        sources=(
            "Glantz, Soviet Military Deception in the Second World War (1989)",
            "Blythe, A History of Operational Art (Military Review, 2018)",
        ),
    ),
    DoctrineProfile(
        key="su-deep-operations", name="Deep operations matured (PU-44)",
        actor="USSR", year_from=1944, year_to=1945,
        tempo=1.18, combined_arms=1.15, flexibility=1.02, set_piece=1.12,
        logistic_reach=1.08, defense_doctrine=1.12,
        summary=("Field Service Regulations (PU-44) codified mature deep "
                 "operations: shock armies breach, mobile groups exploit to "
                 "operational depth - Bagration executed it at scale."),
        sources=(
            "RKKA Field Service Regulations PU-44 (1944)",
            "Glantz, Bagration 1944 (2019)",
        ),
    ),
]

_USA = [
    DoctrineProfile(
        key="us-fm100-5-green", name="FM 100-5 mobilization army (green)",
        actor="USA", year_from=1941, year_to=1942,
        tempo=0.96, combined_arms=0.98, flexibility=0.90, set_piece=1.00,
        logistic_reach=1.15, defense_doctrine=1.00,
        summary=("Doctrine codified in FM 100-5 (1941), heavily influenced by "
                 "impressions of German blitzkrieg; the force itself was green "
                 "- Kasserine exposed immature command and air-ground work."),
        sources=(
            "US Army FM 100-5 Field Service Regulations: Operations (1941)",
            "AHEC Modernization & Readiness Study (doctrine lineage note)",
        ),
    ),
    DoctrineProfile(
        key="us-firepower-logistics", name="Firepower-first / air-ground doctrine",
        actor="USA", year_from=1943, year_to=1945,
        tempo=1.00, combined_arms=1.15, flexibility=1.00, set_piece=1.05,
        logistic_reach=1.22, defense_doctrine=1.08,
        summary=("Methodical firepower-first attacks backed by unmatched "
                 "logistics and fighter-bomber air-ground integration; "
                 "deliberate but relentless once committed."),
        sources=(
            "US Army FM 100-5 (1941) lineage; Doubler, Closing with the Germans (1994)",
            "Gabel, The U.S. Army GHQ Maneuvers of 1941 (1991)",
        ),
    ),
]

_BRITAIN = [
    DoctrineProfile(
        key="uk-interwar-improvisation", name="Interwar inheritance / desert improvisation",
        actor="Great Britain", year_from=1939, year_to=1941,
        tempo=0.96, combined_arms=0.94, flexibility=0.95, set_piece=1.02,
        logistic_reach=1.05, defense_doctrine=1.06,
        summary=("Underfunded interwar doctrine development; desert war saw "
                 "ad-hoc Jock columns and poor armour-infantry-air coordination "
                 "until late 1942."),
        sources=(
            "Lyman & Dannatt, Victory to Defeat: The British Army 1918-1940 (2023)",
            "French, Raising Churchill's Army (2000)",
        ),
    ),
    DoctrineProfile(
        key="uk-set-piece", name="Montgomery set-piece attrition",
        actor="Great Britain", year_from=1942, year_to=1945,
        tempo=0.92, combined_arms=1.08, flexibility=0.95, set_piece=1.20,
        logistic_reach=1.10, defense_doctrine=1.10,
        summary=("From Auchinleck's stand at Alamein line / Montgomery's "
                 "command (Aug 1942): methodical, artillery-heavy 'colossal "
                 "crack' battles fought to a strict time-table (Alam Halfa, "
                 "Alamein, Goodwood): concentration and preparation over "
                 "improvisation; exploitation deliberately cautious. "
                 "Air-ground integration reached parity ~2nd Alamein."),
        sources=(
            "Principles of War podcast ep.108 w/ R. Lyman (competition for superior doctrine)",
            "Carver, El Alamein (1962); French (2000)",
        ),
    ),
]

_JAPAN = [
    DoctrineProfile(
        key="jp-seishin-offensive", name="Seishin offensive / night infiltration",
        actor="Japan", year_from=1937, year_to=1942,
        tempo=1.08, combined_arms=0.85, flexibility=1.05, set_piece=0.92,
        logistic_reach=0.80, defense_doctrine=0.95,
        summary=("Infantry-centric doctrine built on Seishin Kyoiku spiritual "
                 "training: aggressive infiltration, night attacks, bayonet "
                 "assaults. Weak armor/artillery integration and strategic "
                 "logistics; world-class carrier aviation separate from army."),
        sources=(
            "IJA tactical doctrine analyses (Seishin Kyoiku / infantry manuals)",
            "Drea, In the Service of the Emperor (1998)",
        ),
    ),
    DoctrineProfile(
        key="jp-island-defence", name="Island defence in depth",
        actor="Japan", year_from=1943, year_to=1945,
        tempo=0.90, combined_arms=0.88, flexibility=1.00, set_piece=0.90,
        logistic_reach=0.75, defense_doctrine=1.28,
        summary=("Abandoned beach-line annihilation tactics for fortified zones "
                 "in depth - cave systems, registered mortars, local "
                 "counterattacks (Tarawa, Peleliu, Iwo Jima)."),
        sources=(
            "US War Dept intelligence bulletins, Japanese in Battle (1944-45)",
            "Rottman, Japanese Army in World War II (2005)",
        ),
    ),
]

_FRANCE = [
    DoctrineProfile(
        key="fr-continuous-front", name="Methodical continuous front",
        actor="France", year_from=1939, year_to=1940,
        tempo=0.82, combined_arms=0.85, flexibility=0.78, set_piece=1.00,
        logistic_reach=0.95, defense_doctrine=1.15,
        summary=("Pétainist continuous-front legacy: rigid top-down command, "
                 "HQs far forward of radios, armour dispersed for front duty. "
                 "Fortified defence strong (Maginot) but brittle against "
                 "operational surprise (Sedan 1940)."),
        sources=(
            "Doughty, The Seeds of Disaster (1985)",
            "Horne, To Lose a Battle (1969)",
        ),
    ),
]

_ITALY = [
    DoctrineProfile(
        key="it-regio-esercito", name="Regio Esercito (under-resourced)",
        actor="Italy", year_from=1935, year_to=1945,
        tempo=0.88, combined_arms=0.82, flexibility=0.90, set_piece=0.95,
        logistic_reach=0.78, defense_doctrine=0.98,
        summary=("Doctrine copied German patterns but industry could not equip "
                 "it: scarce motor transport, weak artillery allocation, "
                 "inter-service rivalry crippled logistics."),
        sources=(
            "Knox, Mussolini Unleashed 1939-1941 (1982)",
            "Sadkovich, The Italian Navy in WWII (1994) + ground-force studies",
        ),
    ),
]

_FINLAND = [
    DoctrineProfile(
        key="fi-motti-winter", name="Motti tactics / winter warfare",
        actor="Finland", year_from=1939, year_to=1945,
        tempo=1.05, combined_arms=0.90, flexibility=1.15, set_piece=0.90,
        logistic_reach=0.90, defense_doctrine=1.30,
        summary=("Ski troops cut columns into motti pockets; mastery of forest "
                 "and winter terrain, marksmanship, small-unit initiative."),
        sources=(
            "Trotter, A Frozen Hell (1991)",
            "Edwards, White Death: Finland's War with Russia (2006)",
        ),
    )
]

_TIMELINES = {
    "Germany": _GERMANY,
    "USSR": _USSR,
    "USA": _USA,
    "Great Britain": _BRITAIN,
    "Japan": _JAPAN,
    "France": _FRANCE,
    "Italy": _ITALY,
    "Finland": _FINLAND,
}

_ACTOR_ALIASES = {
    "soviet union": "USSR",
    "russia": "USSR",
    "united states": "USA",
    "us": "USA",
    "america": "USA",
    "britain": "Great Britain",
    "uk": "Great Britain",
    "united kingdom": "Great Britain",
    "commonwealth": "Great Britain",
    "australia": "Great Britain",
    "new zealand": "Great Britain",
    "canada": "Great Britain",
    "india": "Great Britain",
    "south africa": "Great Britain",
}

_GENERIC = DoctrineProfile(
    key="generic-contemporary", name="Generic contemporary doctrine",
    actor="", year_from=-9999, year_to=9999,
    summary="No nation-specific doctrine recorded for this actor; neutral effects.",
)


def normalize_actor(actor: str) -> str:
    a = (actor or "").strip()
    return _ACTOR_ALIASES.get(a.lower(), a)


def resolve_doctrine(actor: str, year: int) -> DoctrineProfile:
    """Resolve the doctrine practiced by ``actor`` in ``year``.

    Falls back to a neutral generic profile for unknown actors or years.
    """
    timeline = _TIMELINES.get(normalize_actor(actor))
    if not timeline:
        return _GENERIC
    for profile in timeline:
        if profile.year_from <= year <= profile.year_to:
            return profile
    # Year outside all recorded periods -> nearest neutral fallback.
    return _GENERIC


def attacker_power_mult(doc: DoctrineProfile, terrain: str,
                        duration_hours: float) -> float:
    tokens = {t.strip().lower() for t in (terrain or "").split(",") if t.strip()}
    open_terrain = bool(tokens) and any(t in OPEN_TERRAIN for t in tokens)
    tempo_eff = doc.tempo if open_terrain else 1.0 + (doc.tempo - 1.0) * 0.5
    m = tempo_eff
    m *= 1.0 + (doc.combined_arms - 1.0) * 0.6
    prep = min(max(duration_hours, 0.0) / 24.0, 1.0)     # deliberate prep needs ~a day
    m *= 1.0 + (doc.set_piece - 1.0) * prep
    extra_days = max(min(max(duration_hours, 0.0), 96.0) - 24.0, 0.0) / 72.0
    m *= 1.0 + (doc.logistic_reach - 1.0) * extra_days
    return m


def defender_power_mult(doc: DoctrineProfile) -> float:
    return doc.defense_doctrine * (1.0 + (doc.combined_arms - 1.0) * 0.4)
