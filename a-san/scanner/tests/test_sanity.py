"""Tests for the designation sanity gate (news-headline rejection)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scan.sanity import looks_like_news_headline


HEADLINES = [
    "China Officially Confirms Its J-10 Fighter Shot Down a Rafale During Pakistan-India Fighting",
    "How Many Used JAS 39 Gripen C/D Fighters Could Ukraine Receive if Deliveries Start in 2026?",
    "Eurofighter Typhoon Tranche 4 Takes Flight, Giving Europe a Powerful New Rival",
    "Defense Express' Weekly Review: russia Unveils Skorlupa USV, Colombia Chooses Gripen",
    "After A330 Tankers, MiG-29 Transfer, Poland Considers F-15EX, Korean KF-21 for Air Force",
    "Analysis - Russian Status-6 aka KANYON nuclear deterrence and Pr 09851 submarine",
    "Another Narco-Submarine Found In Colombian Jungle",
    "2 Rare Disguised Narco Submarines Discovered On Trans-Atlantic Route",
    "Where are the Carriers?",
    "List top most modern army military radars in the world",
]

LEGIT_NAMES = [
    "SCALP EG / Storm Shadow / SCALP Naval / Black Shaheen / APACHE AP",
    "Manurhin Special Police revolver, Manurhin MR-88 revolver",
    "KAI / Airbus Helicopters Light Armed Helicopter (LAH)",
    "Boeing (McDonnell Douglas) F/A-18 Hornet",
    "Fairchild Republic A-10 Thunderbolt II (Warthog)",
    "Panavia Tornado ADV (Air Defense Variant)",
    "Boeing E-3 Sentry (AWACS)",
    "M38 SDMR Squad Designated Marksman Rifle",
    "T-AKR 295 Shughart / Large, Medium-speed, roll-on/roll-off ships [LMSR]",
    "Visibility and Management of Operating and Support Costs System\n(VAMOSC)",
    "F-15E Strike Eagle",
    "Electronic Warfare Troops of the Russian Federation",
]


def test_headlines_rejected():
    for h in HEADLINES:
        assert looks_like_news_headline(h), f"should reject: {h[:60]}"


def test_legit_names_pass():
    for n in LEGIT_NAMES:
        assert not looks_like_news_headline(n), f"false positive: {n[:60]}"


def test_empty_and_junk():
    assert not looks_like_news_headline("")
    assert looks_like_news_headline(None) is False
