"""Tests for the round-4 parsers (navweaps, rheinmetall, gdls, oshkosh)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scan.parsers_navweaps import (
    parse_navweaps, parse_navweaps_missile_links, is_navweaps_missile_detail,
    parse_navweaps_main_listing)
from scan.parsers_rheinmetall import parse_rheinmetall
from scan.parsers_gdls import parse_gdls
from scan.parsers_oshkosh import parse_oshkosh, categorize_oshkosh_url

SAMPLES = Path("/tmp/opencode/samples")

TOMAHAWK = """<html><head><title>Tomahawk - Naval Missiles of the United States of America - NavWeaps</title></head>
<body><header><h1>NavWeaps</h1></header>
<h1>Tomahawk BGM-109</h1>
<h2>Description</h2>
<p>Tomahawk is a long-range, all-weather, subsonic cruise missile used from ships and submarines. It first entered service in 1983 and has been upgraded through several blocks.</p>
<h2>Characteristics</h2>
<table class="prettytable">
<tr><th>Designation</th><td>Tomahawk Cruise Missile</td></tr>
<tr><th>Ship Class Used On</th><td>Cruisers, Destroyers and Submarines</td></tr>
<tr><th>Date In Service</th><td>1990</td></tr>
<tr><th>Range</th><td>1,350 nm for nuclear<br>approx. 1,000 nm for others</td></tr>
</table></body></html>"""

WMUS_MAIN = """<html><body>
<a href="WMUS_Tomahawk.php">Tomahawk</a>
<a href="WMUS_Trident-D5.php">Trident II D5</a>
<a href="index_weapons.php">Index</a>
<a href="WMUS_Main.php">Main</a>
</body></html>"""

RHEIN = """<html><head><title>Mission Master – Uncrewed Ground Vehicles family (UGV) | Rheinmetall</title>
<meta name="description" content="The Mission Master family of uncrewed ground vehicles."></head>
<body><div class="wysiwyg"><p>The Mission Master family delivers autonomous transport.</p></div>
<h2>Mission Master SP2</h2><h2>Mission Master CXT2</h2></body></html>"""

GDLS = """<html><head><title>TRACKED ROBOT 10-TON (TRX) - General Dynamics Land Systems</title></head>
<body><h2>TRX BREACHER</h2><h2>TRX SHORAD</h2>
<p>The TRX is an autonomous tracked robotic platform for counter-UAS missions.</p></body></html>"""

OSH = """<html><head><title>HEMTT (Heavy Expanded Mobility Tactical Truck) | Oshkosh Defense</title>
<meta name="description" content="HEMTT trucks support cargo, fuel, and recovery operations in the field."></head>
<body><h1>HEMTT A4</h1><p>Built for rugged terrain.</p></body></html>"""


def test_navweaps_detail():
    e = parse_navweaps("https://www.navweaps.com/Weapons/WMUS_Tomahawk.php", TOMAHAWK)
    assert e is not None
    assert "Tomahawk" in e.designation
    assert e.country == "USA"
    assert any(s.startswith("Range:") for s in e.specs)
    assert e.category == "Sea-launched cruise missiles"
    assert e.sources[0].url.endswith("WMUS_Tomahawk.php")


def test_navweaps_links():
    links = parse_navweaps_missile_links(WMUS_MAIN)
    assert links == ["https://www.navweaps.com/Weapons/WMUS_Tomahawk.php",
                     "https://www.navweaps.com/Weapons/WMUS_Trident-D5.php"]
    assert is_navweaps_missile_detail(links[0])
    assert not is_navweaps_missile_detail(
        "https://www.navweaps.com/Weapons/WMUS_Main.php")
    # 3- and 4-letter country codes (WMRUS, WMARG) must match too
    long = parse_navweaps_missile_links(
        '<a href="WMRUS_R-11FM.php">R-11FM</a><a href="WMARG_Main.php">x</a>'
        '<a href="WMFR_Exocet.php">Exocet</a>')
    assert "https://www.navweaps.com/Weapons/WMRUS_R-11FM.php" in long
    assert "https://www.navweaps.com/Weapons/WMFR_Exocet.php" in long
    assert not any("Main" in u for u in long)
    assert is_navweaps_missile_detail(
        "https://www.navweaps.com/Weapons/WMRUS_RSM-54.php")


def test_navweaps_tartar_not_slcm():
    """'missile cruisers' in prose must not read as a cruise marker."""
    tartar = TOMAHAWK.replace("Tomahawk", "Tartar").replace(
        "BGM-109", "RIM-24").replace(
        "long-range, all-weather, subsonic cruise missile",
        "medium-range naval SAM used on missile cruisers and destroyers")
    e = parse_navweaps("https://www.navweaps.com/Weapons/WMUS_Tartar-RIM24.php",
                       tartar)
    assert e is not None
    assert e.category == "Rocket and missile weapons"


def test_navweaps_main_listing():
    main = """<html><head><title>Naval Missiles of Russia/USSR - NavWeaps</title></head>
<body><h1>Naval Missiles of Russia/USSR</h1>
<h2>Anti-Ship Missiles</h2>
<table class="prettytable">
<tr><td>P-15 Termit</td><td>4K-40</td><td>SSN-2A Styx</td><td>first Soviet tactical anti-ship missile.</td></tr>
<tr><td>P-500 Bazalt</td><td>4K80</td><td>SSN-12 Sandbox</td><td>Long-range supersonic anti-ship missile.</td></tr>
</table>
<h2>Anti-Aircraft Missiles</h2>
<table class="prettytable">
<tr><td>M-1 Volna</td><td>4K90</td><td>SA-N-1 Goa</td><td>Naval version of the SA-3.</td></tr>
</table>
<h2>Missile Launchers</h2>
<table class="prettytable"><tr><td>RBU-1000</td><td></td><td></td><td>Six-barrelled rocket launcher.</td></tr></table>
</body></html>"""
    entries = parse_navweaps_main_listing(
        "https://www.navweaps.com/Weapons/WMRUS_Main.php", main)
    cats = {e.designation: e.category for e in entries}
    assert cats == {"P-15 Termit": "Sea-launched cruise missiles",
                    "P-500 Bazalt": "Sea-launched cruise missiles",
                    "M-1 Volna": "Rocket and missile weapons"}
    p15 = entries[0]
    assert p15.country == "Russia/USSR"
    assert "NATO Codename: SSN-2A Styx" in p15.specs
    assert "Industry Code: 4K-40" in p15.specs
    assert "SSN-2A Styx" in p15.alt_names


def test_rheinmetall():
    e = parse_rheinmetall(RHEINMETALL_URL, RHEIN)
    assert e is not None
    assert e.designation == "Mission Master"
    assert e.manufacturer == "Rheinmetall"
    assert "Mission Master SP2" in e.alt_names
    assert e.category == "UGVs"


RHEINMETALL_URL = ("https://www.rheinmetall.com/en/products/"
                   "uncrewed-systems-and-autonomous-navigation-technology/"
                   "mission-master-a-ugs")


def test_gdls():
    e = parse_gdls("https://www.gdls.com/trx-fov/", GDLS, "UGVs")
    assert e is not None
    assert e.designation == "TRACKED ROBOT 10-TON (TRX)"
    assert "TRX BREACHER" in e.alt_names
    assert e.category == "UGVs"
    assert e.country == "USA"


def test_oshkosh():
    url = "https://oshkoshdefense.com/vehicles/heavy-tactical-vehicles/hemtt/"
    e = parse_oshkosh(url, OSH, "Automotive vehicles")
    assert e is not None
    assert e.designation == "HEMTT"
    assert "Heavy Expanded Mobility Tactical Truck" in e.alt_names
    assert "cargo, fuel" in e.description


def test_oshkosh_categorize():
    assert categorize_oshkosh_url(
        "https://oshkoshdefense.com/vehicles/light-tactical-vehicles/jltv/") \
        == "Automotive vehicles"
    # combat-vehicle marketing pages have no per-product designation -> skip
    assert categorize_oshkosh_url(
        "https://oshkoshdefense.com/vehicles/combat-vehicles/rcv/") is None
    # class hub pages are not product entries -> skip
    assert categorize_oshkosh_url(
        "https://oshkoshdefense.com/vehicles/heavy-tactical-vehicles/") is None
    assert categorize_oshkosh_url(
        "https://oshkoshdefense.com/about/") is None
    assert categorize_oshkosh_url(
        "https://oshkoshdefense.com/vehicles/mine-resistant-ambush-protected-mrap/") \
        == "Armored vehicles and equipment"


def test_live_samples():
    """Re-parse the live-fetched sample HTML fixtures when present."""
    f = SAMPLES / "tomahawk.html"
    if not f.exists():
        return
    e = parse_navweaps("https://www.navweaps.com/Weapons/WMUS_Tomahawk.php",
                       f.read_text(encoding="utf-8", errors="replace"))
    assert e is not None and "Tomahawk" in e.designation
    assert e.category == "Sea-launched cruise missiles"
    assert len(e.specs) >= 4
