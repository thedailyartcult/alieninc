"""Tests for the round-6 parsers (elbitsystems, amgeneral)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scan.parsers_elbit import parse_elbit, elbit_category_for
from scan.parsers_amgeneral import parse_amgeneral

ELBIT = """<html><head><title>COMBATGUARD Armored Fighting Vehicle AFV | Elbit Systems</title>
<meta property="og:title" content="COMBATGUARD">
<meta name="description" content="Conquer any terrain with the COMBATGUARD, a high-speed 4x4 Armored Fighting Vehicle."></head>
<body>
<div class="field--name-field-teaser field--type-string-long field__item">- Road speed max: 120km/h (75m/h)<br />
- Operational range: 600km (on road)<br />
- Curb Weight: 11,300 kg<br />
- Payload: 1,500 kg<br />
- Crew: 6/8 fully equipped troops</div>
</body></html>"""

AMG = """<html><head><title>Humvee 4-CT</title>
<meta property="og:title" content="Humvee 4-CT">
<meta name="description" content="The Humvee 4-CT is the four-door cargo variant."></head>
<body>
<div class="x-text x-content a"><span class="beachwood-wide">GVW</span></div>
<div class="x-text x-content b"><p>12,100 lb. (5,488 kg)</p></div>
<div class="x-text x-content c"><span class="beachwood-wide">POWERTRAIN</span></div>
<div class="x-text x-content d"><p>4-speed automatic transmission</p>
<p>V8, 6.5L turbocharged diesel engine</p>
<p>190 hp @ 3,400 rpm</p></div>
<div class="x-text x-content e"><span class="beachwood-wide">DOWNLOAD</span></div>
<div class="x-text x-content f"><p>brochure.pdf</p></div>
</body></html>"""


def test_elbit_category_routing():
    base = "https://elbitsystems.com/land"
    assert elbit_category_for(f"{base}/combat-vehicle-systems/x/y") == \
        "Armored vehicles and equipment"
    assert elbit_category_for(f"{base}/bridges/a/b") == \
        "Armored vehicles and equipment"
    assert elbit_category_for(
        f"{base}/weapons-systems-and-munitions/missiles-rockets/extra") == \
        "Rocket and missile weapons"
    assert elbit_category_for(f"{base}/ammunition/x") == \
        "Rocket and missile weapons"
    assert elbit_category_for(f"{base}/land-ew-sigint/a/b") == "EW assets"
    assert elbit_category_for(f"{base}/land-c4isr/a/b") == "EW assets"
    assert elbit_category_for(f"{base}/infantry/ammunition/y") == \
        "Rocket and missile weapons"
    assert elbit_category_for(f"{base}/infantry/weapons/y") == "Small arms"
    # training-systems deliberately unrouted
    assert elbit_category_for(f"{base}/training-systems/a/b") == ""


def test_elbit_parse():
    url = ("https://elbitsystems.com/land/combat-vehicle-systems/"
           "armored-fighting-vehicle/combatguard")
    e = parse_elbit(url, ELBIT, "Armored vehicles and equipment")
    assert e is not None
    assert e.designation == "COMBATGUARD"
    assert e.country == "Israel"
    assert e.manufacturer == "Elbit Systems"
    assert "Payload: 1,500 kg" in e.specs
    assert any(s.startswith("Operational range:") for s in e.specs)
    assert "high-speed 4x4" in e.description
    assert e.sources[0].url == url


def test_elbit_skips_hubs():
    hub = """<html><head><title>Combat Vehicle Systems | Elbit Systems</title>
<meta name="description" content="Overview"></head><body><p>hub</p></body></html>"""
    assert parse_elbit("https://elbitsystems.com/land/combat-vehicle-systems/",
                       hub, "") is None
    assert parse_elbit("https://example.com/land/x/y/", ELBIT) is None


def test_amgeneral_parse():
    url = "https://www.amgeneral.com/humvee-4ct"
    e = parse_amgeneral(url, AMG)
    assert e is not None
    assert e.designation == "Humvee 4-CT"
    assert e.country == "United States"
    assert e.manufacturer == "AM General"
    assert e.category == "Automotive vehicles"
    specs = "\n".join(e.specs)
    assert "POWERTRAIN: 4-speed automatic transmission" in specs
    assert any(s.startswith("GVW: ") and "5,488" in s for s in e.specs)
    # DOWNLOAD section filtered; brochure line absent
    assert "brochure" not in specs


def test_amgeneral_rejects_foreign():
    assert parse_amgeneral("https://example.com/x", AMG) is None
