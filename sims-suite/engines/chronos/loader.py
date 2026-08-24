"""Load historical battles from panteon.db into Chronos engine models."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from .models import HistoricalBattle, HistoricalSide

DEFAULT_DB = Path(__file__).resolve().parents[3] / "panteon" / "backend" / "panteon.db"

_YEAR_RE = re.compile(r"(1[6-9]\d{2}|20[0-2]\d)")


def _extract_year(text: str) -> Optional[int]:
    if not text:
        return None
    matches = _YEAR_RE.findall(text)
    return int(matches[-1]) if matches else None


def _actors(raw: Optional[str]) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def load_battle(isqno: int, db_path: Path = DEFAULT_DB) -> Optional[HistoricalBattle]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        b = conn.execute(
            "SELECT * FROM chronos_battles WHERE isqno = ?", (isqno,)
        ).fetchone()
        if not b:
            return None
        bels = conn.execute(
            """SELECT * FROM chronos_belligerents WHERE isqno = ?
               ORDER BY side DESC, strength DESC""",
            (isqno,),
        ).fetchall()
    finally:
        conn.close()

    attacking = [r for r in bels if r["side"] == 1]
    defending = [r for r in bels if r["side"] == 0]

    def make_side(rows) -> HistoricalSide:
        if not rows:
            return HistoricalSide(side_id=0)
        primary = rows[0]
        strength = sum((r["strength"] or 0) for r in rows)
        casualties = sum((r["casualties"] or 0) for r in rows)
        return HistoricalSide(
            side_id=primary["side"],
            unit_name=primary["unit_name"],
            commander=primary["commander"],
            strength=float(strength),
            casualties=float(casualties),
            tanks=sum((r["tank"] or 0) + (r["mbt"] or 0) + (r["ltank"] or 0) for r in rows),
            artillery=sum((r["arty"] or 0) for r in rows),
            aircraft=sum((r["aircraft"] or 0) for r in rows),
            cavalry=sum((r["cav"] or 0) for r in rows),
            leadership=primary["leadership"],
            training=primary["training"],
            morale=primary["morale"],
            logistics=primary["logistics"],
            tech=primary["tech"],
            surprise=primary["surprise"],
            result_code=primary["result_code"],
        )

    year = None
    for text in (b["campaign"], b["war"], b["start_date"]):
        year = year or _extract_year(text or "")
    year = year or 1900

    battle_key = f"cdb90-{isqno}"
    attacker = make_side(attacking)
    defender = make_side(defending)
    attacker.actors = _actors(b["attacker_actors"])
    defender.actors = _actors(b["defender_actors"])

    return HistoricalBattle(
        battle_key=battle_key,
        name=b["name"],
        war=b["war"] or "",
        year=int(year),
        terrain=b["terrain"] or "open",
        weather=b["weather"] or "",
        duration_hours=float(b["duration_hours"] or 24.0),
        attacker=attacker,
        defender=defender,
        air_superiority=int(b["air_superiority"] or 0) if "air_superiority" in b.keys() else 0,
        source=b["source"] or "CDB90",
    )


def get_oob(battle_key: str, db_path: Path = DEFAULT_DB) -> list[dict]:
    """Orders of battle for a battle key (curated flagship entries)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT oob_id, side, echelon, unit_name, parent, strength,
                      equipment_json, engagement_fraction, source, confidence
               FROM chronos_oob WHERE battle_key = ?
               ORDER BY CASE WHEN parent IS NULL THEN 0 ELSE 1 END, strength DESC""",
            (battle_key,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["equipment"] = json.loads(d.pop("equipment_json") or "{}")
            except json.JSONDecodeError:
                d["equipment"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def load_curated_battle(battle_key: str, db_path: Path = DEFAULT_DB) -> Optional[HistoricalBattle]:
    """Build a HistoricalBattle from chronos_oob entries alone (battles not in
    the CDB90 corpus, e.g. 'curated-neptune-1944'). Top-level entries per side
    provide strengths; year parsed from the key suffix. Recorded outcomes come
    from the ``_meta.outcomes`` block of the curated JSON (synced into
    chronos_sync_meta as part of the OOB import)."""
    entries = get_oob(battle_key, db_path)
    if not entries:
        return None

    meta_path = db_path  # outcome map lives next to the data file in DATA_DIR
    outcome = _curated_outcome(battle_key)

    year = None
    for part in battle_key.split("-"):
        if part.isdigit() and 1300 < int(part) < 2100:
            year = int(part)
            break


    def _is_top(e) -> bool:
        parent = e.get("parent")
        if not parent:
            return True
        for other in entries:
            un, pn = other["unit_name"], parent
            if un == pn or un.startswith(pn) or pn.startswith(un):
                return False
        return True

    def build_side(side: str, side_id: int) -> HistoricalSide:
        tops = [e for e in entries if e["side"] == side and _is_top(e)]
        names = [e["unit_name"] for e in tops]
        strength = 0.0
        tanks = arty = air = cav = 0
        quality: dict[str, float] = {}
        surprise_vals = []
        for e in tops:
            # engagement_fraction: share of the formation actually in contact
            # (amphibious/theatre-level forces are rarely fully committed).
            frac = float(e.get("engagement_fraction") if e.get("engagement_fraction") is not None else 1.0)
            strength += (e.get("strength") or 0) * frac
            eq = e.get("equipment") or {}
            tanks += int(eq.get("tanks") or eq.get("tanks_landed_d1") or 0)
            arty += int(eq.get("artillery") or 0)
            air += int(eq.get("aircraft") or eq.get("aircraft_sorties_d1") or 0)
            cav += int(eq.get("cavalry") or 0)
            for q in ("leadership", "training", "morale", "logistics", "tech"):
                if q in eq:
                    quality[q] = max(quality.get(q, 0.0), float(eq[q]))
            if "surprise" in eq:
                surprise_vals.append(float(eq["surprise"]))
        s = HistoricalSide(side_id=side_id, strength=float(strength),
                           actors=names, tanks=tanks, artillery=arty,
                           aircraft=air, cavalry=cav,
                           leadership=quality.get("leadership"),
                           training=quality.get("training"),
                           morale=quality.get("morale"),
                           logistics=quality.get("logistics"),
                           tech=quality.get("tech"),
                           surprise=max(surprise_vals) if surprise_vals else None)
        return s

    att_str_side = build_side("attacker", 1)
    dfd_side = build_side("defender", 0)
    if outcome:
        code = outcome.get("result_code")
        if outcome.get("winner") == "attacker":
            att_str_side.result_code = code or "BB"
            dfd_side.result_code = "RR"
        else:
            dfd_side.result_code = code or "BB"
            att_str_side.result_code = "RR"

    return HistoricalBattle(
        battle_key=battle_key,
        name=battle_key.replace("-", " ").replace("curated ", "").upper(),
        war="CURATED",
        year=year or 1944,
        terrain="mixed",
        duration_hours=48.0,
        attacker=att_str_side,
        defender=dfd_side,
        source="chronos_oob",
    )


_CURATED_OUTCOMES_CACHE: Optional[dict] = None


def _curated_outcome(battle_key: str) -> Optional[dict]:
    global _CURATED_OUTCOMES_CACHE
    try:
        meta_file = Path(__file__).resolve().parents[2] / "data" / "chronos" / "oob_flagships.json"
        if _CURATED_OUTCOMES_CACHE is None:
            payload = json.loads(meta_file.read_text())
            _CURATED_OUTCOMES_CACHE = payload.get("_meta", {}).get("outcomes", {})
        return _CURATED_OUTCOMES_CACHE.get(battle_key)
    except Exception:
        return None


def search_battles(db_path: Path = DEFAULT_DB, war_filter: str = "",
                   limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        sql = """SELECT isqno, name, war, campaign, location, start_date,
                        duration_hours, terrain, weather
                 FROM chronos_battles"""
        params: list = []
        if war_filter:
            sql += " WHERE war LIKE ? OR name LIKE ?"
            params += [f"%{war_filter}%", f"%{war_filter}%"]
        sql += " ORDER BY isqno LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def country_power(stateabb_or_ccode: str | int, year: int,
                  db_path: Path = DEFAULT_DB) -> Optional[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """SELECT * FROM chronos_countries
               WHERE (stateabb = ? OR ccode = ?) AND year = ?""",
            (str(stateabb_or_ccode), stateabb_or_ccode, year),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def top_powers(year: int, limit: int = 10, db_path: Path = DEFAULT_DB) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT stateabb, ccode, milex, milper, irst, pec, tpop, upop, cinc
               FROM chronos_countries WHERE year = ?
               ORDER BY cinc DESC LIMIT ?""",
            (year, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
