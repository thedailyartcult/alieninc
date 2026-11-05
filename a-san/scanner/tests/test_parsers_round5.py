"""Tests for the round-5 parsers (naval-encyclopedia, qinetiq)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scan.parsers_navalencyclopedia import (
    parse_naval_encyclopedia, is_naval_encyclopedia_ship_url)
from scan.parsers_qinetiq import parse_qinetiq

SHIP = """<html><head><title>Majestic class aircraft carriers &#8211; naval encyclopedia</title></head>
<body>
<h1>Majestic class aircraft carriers</h1>
<p>The Majestic class was a modified Colossus-class design completed after WW2 for the Royal Navy and Commonwealth navies. Several were sold or transferred to friendly fleets.</p>
<table>
<tr><td>&#9881; specifications</td></tr>
<tr><td>Displacement</td><td>14,000t standard, 17,780 t FL</td></tr>
<tr><td>Propulsion</td><td>2x Parsons GST</td></tr>
<tr><td>Speed</td><td>25 knots (46 km/h)</td></tr>
</table>
<p>Later ships served in Australia and India well into the 1980s.</p>
</body></html>"""

QINETIQ = """<html><head><title>Bomb Disposal Robot - QinetiQ</title>
<meta name="description" content="TALON can be used as a bomb disposal robot, for reconnaissance and heavy lift."></head>
<body><h1>TALON&#174; Medium-Sized Tactical Robot</h1>
<p>Since its introduction in 2000, QinetiQ's TALON family of robots have earned a reputation for durability.</p></body></html>"""


def test_ne_ship_url():
    assert is_naval_encyclopedia_ship_url(
        "https://naval-encyclopedia.com/cold-war/uk/tiger-class-cruisers.php")
    assert is_naval_encyclopedia_ship_url(
        "https://www.naval-encyclopedia.com/ww2/us/fletcher-class-destroyers.php")
    # non-article paths rejected
    assert not is_naval_encyclopedia_ship_url(
        "https://naval-encyclopedia.com/naval-battles/battle-salamis-480-bc.php")
    assert not is_naval_encyclopedia_ship_url(
        "https://naval-encyclopedia.com/prehistoric-boats.php")
    assert not is_naval_encyclopedia_ship_url(
        "https://naval-encyclopedia.com/cold-war/uk/")
    assert not is_naval_encyclopedia_ship_url("https://example.com/ww2/uk/x.php")


def test_ne_parse():
    url = ("https://naval-encyclopedia.com/cold-war/uk/"
           "majestic-class-aircraft-carriers.php")
    e = parse_naval_encyclopedia(url, SHIP)
    assert e is not None
    assert e.designation == "Majestic class aircraft carriers"
    assert e.country == "UK"
    assert e.category == "Naval vessels"
    assert any(s.startswith("Displacement:") for s in e.specs)
    assert any(s.startswith("Speed:") for s in e.specs)
    assert not any("specification" in s.lower() for s in e.specs)
    assert len(e.description) > 80
    assert e.sources[0].url == url


def test_ne_parse_ussr():
    html = SHIP.replace("&#8211; naval encyclopedia", "- naval encyclopedia")
    e = parse_naval_encyclopedia(
        "https://www.naval-encyclopedia.com/ww2/ussr/chapayev-class-cruisers.php",
        html)
    assert e is not None
    assert e.country == "Russia/USSR"


def test_qinetiq():
    e = parse_qinetiq(
        "https://www.qinetiq.com/en/what-we-do/research-and-development/"
        "autonomous-systems/robotics/robotic-products/"
        "talon-medium-sized-tactical-robot", QINETIQ)
    assert e is not None
    assert e.designation == "TALON Medium-Sized Tactical Robot"
    assert e.manufacturer == "QinetiQ"
    assert e.country == "UK"
    assert e.category == "UGVs"
    assert "bomb disposal robot" in e.description.lower()


def test_ne_no_sitename_designation():
    """The site-name H1 must never become a designation."""
    html = SHIP.replace(
        "Majestic class aircraft carriers &#8211; naval encyclopedia",
        "Maine class battleships - naval encyclopedia").replace(
        "<h1>Majestic class aircraft carriers</h1>",
        "<h1>Naval Encyclopedia</h1>")
    e = parse_naval_encyclopedia(
        "https://www.naval-encyclopedia.com/ww1/us/maine-class-battleships.php",
        html)
    assert e is not None
    assert e.designation == "Maine class battleships"
    assert e.country == "USA"


def test_ne_topic_page_detector():
    from scan.parsers_navalencyclopedia import is_naval_encyclopedia_topic_page
    assert is_naval_encyclopedia_topic_page(
        "https://naval-encyclopedia.com/industrial-era/1860-fleets/french-navy-1860.php")
    assert is_naval_encyclopedia_topic_page(
        "https://naval-encyclopedia.com/ww2/us/amphibious-operations.php")
    assert not is_naval_encyclopedia_topic_page(
        "https://naval-encyclopedia.com/cold-war/uk/tiger-class-cruisers.php")
