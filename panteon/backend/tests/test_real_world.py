"""Tests for real-world anchoring: World Bank ingestion (mocked), arsenal
adapter (fixture catalog), and absolute casualty translation."""
import json

import pytest

from panteon import arsenal
from panteon.real_world import (
    estimate_absolute_casualties,
    fetch_real_country,
)
from panteon.war_ontology import emit_battle_report, graph_snapshot


# ------------------------------------------------------------------ arsenal
@pytest.fixture
def mini_catalog(tmp_path, monkeypatch):
    cat = {
        "schema_version": "1.0", "generated": "test",
        "categories": ["aircraft", "naval-vessels"],
        "category_keys": ["aircraft", "naval-vessels"],
        "entry_counts": {"aircraft": 2, "naval-vessels": 1},
        "total_entries": 3,
        "entries": {
            "aircraft": [
                {"designation": "F-5 Tiger", "country": "Taiwan", "manufacturer": "Northrop",
                 "description": "Light fighter",
                 "specs": ["Maximum Speed: 1,060 mph", "Crew: 2"],
                 "sources": [{"label": "x", "url": "https://x"}],
                 "fetched_at": "2026-08-23T00:00:00+00:00"},
                {"designation": "J-7", "country": "china", "manufacturer": "",
                 "description": "Interceptor",
                 "specs": ["Year: 1966"], "sources": [],
                 "fetched_at": "2026-08-22T00:00:00+00:00"},
            ],
            "naval-vessels": [
                {"designation": "Kee Lung class", "country": "japan maritime self defense force",
                 "manufacturer": "", "description": "Destroyer",
                 "specs": ["Displacement: 9,800 tons"], "sources": [],
                 "fetched_at": "2026-08-21T00:00:00+00:00"},
            ],
        },
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(cat), encoding="utf-8")
    monkeypatch.setattr(arsenal, "CATALOG_PATH", str(path))
    with arsenal._lock:
        arsenal._cache["mtime"] = None
        arsenal._cache["by_category"] = {}
    return path


def test_normalize_country():
    assert arsenal.normalize_country("japan maritime self defense force") == "Japan"
    assert arsenal.normalize_country("royal") == "United Kingdom"
    assert arsenal.normalize_country("Weight") is None
    assert arsenal.normalize_country("Taiwan") == "Taiwan"


def test_capability_counts_and_query(mini_catalog):
    counts = arsenal.capability_counts("TWN")
    assert counts["available"] and counts["country"] == "Taiwan"
    r = arsenal.query_entries(country="Japan", category="naval-vessels")
    assert r["entries"][0]["designation"] == "Kee Lung class"
    assert r["entries"][0]["specs_parsed"]["displacement"] == "9,800 tons"
    search = arsenal.query_entries(q="tiger")
    assert any(e["designation"] == "F-5 Tiger" for e in search["entries"])


def test_curated_flagships_deterministic(mini_catalog):
    a = arsenal.curated_flagships("Taiwan", per_category=2)
    b = arsenal.curated_flagships("Taiwan", per_category=2)
    assert [f["pk"] for f in a] == [f["pk"] for f in b]
    assert len(a) == 1  # only the F-5 is Taiwanese in this fixture


# ------------------------------------------------------- casualty estimates
def test_estimate_absolute_casualties_math():
    report = {"avg_red_casualties": 50.0, "avg_blue_casualties": 25.0}
    baselines = {"red_personnel": 1_000_000.0, "blue_personnel": 200_000.0}
    est = estimate_absolute_casualties(report, baselines, commitment=0.10)
    assert est["est_red_casualties_soldiers"] == 50_000   # 50% of 100k committed
    assert est["est_blue_casualties_soldiers"] == 5_000   # 25% of 20k committed
    assert est["commitment_fraction"] == 0.10


def test_estimate_requires_baselines():
    est = estimate_absolute_casualties({"avg_red_casualties": 50.0}, {})
    assert est is None


# ------------------------------------------------------- world country flow
@pytest.mark.asyncio
async def test_fetch_real_country_shapes(db_session, monkeypatch):
    class FakeResp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    async def fake_get(self, url, params=None):
        if "SP.POP.TOTL" in url:
            return FakeResp([{}, [{"value": 23000000.0, "date": "2023"}]])
        if "MS.MIL.TOTL" in url:
            return FakeResp([{}, [{"value": 169000.0, "date": "2022"}]])
        if "MS.MIL.XPND" in url:
            return FakeResp([{}, []])  # no data -> None
        return FakeResp([{"message": ["?"]}])

    import httpx as _httpx
    monkeypatch.setattr(_httpx.AsyncClient, "get", fake_get)

    async with _httpx.AsyncClient() as client:
        props = await fetch_real_country(client, "TW")
    assert props["population"] == 23000000.0
    assert props["armed_forces_personnel"] == 169000.0
    assert "military_expenditure_usd" not in props  # missing values omitted
    assert props["lat"] == 25.033 and props["lng"] == 121.5654
    assert props["source"] == "world_bank"


@pytest.mark.asyncio
async def test_fetch_fallback_for_non_wb_economy(db_session, monkeypatch):
    class FakeResp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    async def fake_get(self, url, params=None):
        # World Bank has no data for TW — every indicator empty.
        return FakeResp([{}, []])

    import httpx as _httpx
    monkeypatch.setattr(_httpx.AsyncClient, "get", fake_get)

    async with _httpx.AsyncClient() as client:
        props = await fetch_real_country(client, "TW")
    assert props["population"] == 23400000
    assert props["armed_forces_personnel"] == 169000
    assert props["source"] == "curated_fallback"


@pytest.mark.asyncio
async def test_emit_with_real_context_stores_estimates(db_session, battle_report):
    summary = await emit_battle_report(
        db_session, dict(battle_report),
        real_context={"red_personnel": 1_000_000.0, "blue_personnel": 200_000.0,
                      "red_iso": "RUS", "blue_iso": "UKR"})
    assert summary["emitted"]
    snap = await graph_snapshot(db_session)
    assessment = next(n for n in snap["nodes"]
                      if n["type"] == "kriegspiel_assessment")
    # 50.8% of 100k committed red troops
    assert assessment["properties"]["est_red_casualties_soldiers"] == 50800
    # 24.3% of 20k committed blue troops
    assert assessment["properties"]["est_blue_casualties_soldiers"] == 4860
    assert assessment["properties"]["real_anchored"] is True
