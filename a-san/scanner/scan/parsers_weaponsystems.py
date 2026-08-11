"""Parser for weaponsystems.net - structured weapons system data."""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso


def parse_weaponsystem(url: str, html: str, category_display: str = "") -> dict | None:
    """Parse a weaponsystems.net system page into a catalog entry dict.
    
    Returns None if the page cannot be parsed.
    """
    if not html:
        return None
    
    # Title from <title> tag
    title_m = re.search(r'<title>(.*?)</title>', html, re.S)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r'<[^>]+>', '', title_m.group(1)).strip())
    title = title.replace(' | Weaponsystems.net', '').strip()
    if not title:
        return None
    
    # Extract all factsheet data
    specs = []
    description_parts = []
    
    # Find all factsheet sections with their label-value pairs
    sections = re.finditer(
        r'<div[^>]*class="[^"]*factsheetsboxSection[^"]*">.*?<b>([^<]+)</b>(.*?)(?=</div>\s*</div>\s*<div[^>]*class="[^"]*factsheetsboxSection|<div[^>]*class="[^"]*columncontainer)',
        html, re.S)
    
    for section_m in sections:
        section_name = section_m.group(1).strip()
        section_content = section_m.group(2)
        
        # Find all label-value pairs
        rows = re.findall(
            r'<div[^>]*class="[^"]*factsheetsboxCellLeft[^"]*">([^<]*)</div>\s*'
            r'<div[^>]*class="[^"]*factsheetsboxCellRight[^"]*">([^<]+)</div>',
            section_content, re.S)
        
        for label, value in rows:
            label = html_lib.unescape(label.strip())
            value = html_lib.unescape(value.strip())
            if label or value:
                if section_name == "General":
                    if not label and not description_parts:
                        description_parts.append(value)
                    elif label == "Type":
                        description_parts.insert(0, value)
                        specs.append(f"Type: {value}")
                    else:
                        specs.append(f"{label}: {value}" if label else value)
                elif section_name == "Dimensions":
                    specs.append(f"{label}: {value}" if label else value)
                elif section_name == "Propulsion":
                    specs.append(f"{label}: {value}" if label else value)
                elif section_name == "Performance":
                    specs.append(f"{label}: {value}" if label else value)
                elif section_name == "Armament":
                    specs.append(f"{label}: {value}" if label else value)
                elif section_name == "Sensors":
                    specs.append(f"{label}: {value}" if label else value)
                elif section_name == "Avionics":
                    specs.append(f"{label}: {value}" if label else value)
                else:
                    specs.append(f"{label}: {value}" if label else value)
    
    # Extract overview text from related articles section
    overview_m = re.search(r'<div[^>]*class="[^"]*tableblock-2[^"]*">(.*?)</div>', html, re.S)
    overview = ""
    if overview_m:
        overview = html_lib.unescape(re.sub(r'<[^>]+>', '', overview_m.group(1)).strip())
        overview = re.sub(r'\s+', ' ', overview)[:500]
    
    # Build description
    if overview:
        description = overview
    elif description_parts:
        description = f"{title} - {' '.join(description_parts[:2])}. Public technical profile from Weaponsystems.net."
    else:
        description = f"Public technical profile of {title} from Weaponsystems.net."
    
    # Determine category from content if not provided or if it's Uncategorized
    if not category_display or category_display == "Uncategorized":
        category_display = _classify_weaponsystem(title, description, specs)
    
    return CatalogEntry(
        designation=title,
        category=category_display,
        description=description[:600],
        specs=specs[:20],
        sources=[SourceRef('Weaponsystems.net', url)],
        fetched_at=now_iso(),
    )


def _classify_weaponsystem(title: str, description: str, specs: list[str]) -> str:
    """Classify a weaponsystem.net entry into one of our catalog categories."""
    text = f"{title} {description} {' '.join(specs)}".lower()
    
    # First check if this is a WEAPON (gun, missile, etc.) vs a PLATFORM (aircraft, vehicle, ship)
    # Weapons can mention platforms they're mounted on, but they're not platforms themselves
    is_weapon = False
    is_platform = False
    
    # Check the "Type" spec if available
    for spec in specs:
        if spec.lower().startswith('type:'):
            type_val = spec[5:].strip().lower()
            if any(kw in type_val for kw in ('gun', 'missile', 'rocket', 'rifle', 'pistol', 'cannon',
                                              'mortar', 'howitzer', 'artillery', 'minigun', 'launcher',
                                              'bomb', 'torpedo', 'ammunition')):
                is_weapon = True
            elif any(kw in type_val for kw in ('helicopter', 'aircraft', 'tank', 'ship', 'vehicle',
                                                'apc', 'ifv', 'destroyer', 'frigate', 'submarine',
                                                'carrier', 'corvette', 'cruiser', 'uav', 'drone')):
                is_platform = True
            break
    
    # Order matters - check for platform types first, then weapons
    # Aircraft (including helicopters)
    aircraft_kws = ['helicopter', 'attack helicopter', 'transport helicopter', 'utility helicopter',
                    'fighter ', 'bomber', 'transport aircraft', 'trainer aircraft', 'reconnaissance aircraft',
                    'aircraft', 'jet ', 'rotor']
    model_prefixes = ['mi-', 'ka-', 'ah-', 'uh-', 'ch-', 'mh-', 'oh-',
                      'su-', 'mig-', 'tu-', 'il-', 'an-', 'yak-']
    
    import re
    is_aircraft = any(kw in text for kw in aircraft_kws)
    if not is_aircraft:
        for prefix in model_prefixes:
            if re.search(r'(?:^|[\s(,])' + re.escape(prefix), text):
                is_aircraft = True
                break
    
    # If it's clearly a weapon (by Type spec), skip platform classification
    if is_weapon and not is_platform:
        # Classify as weapon
        if any(kw in text for kw in ('missile', 'rocket', 'tow', 'stinger', 'javelin', 'hellfire', 'cruise',
                                      'ballistic', 'atgm', 'anti-tank guided', 'surface-to-air', 'air-to-air',
                                      'air-to-surface', 'surface-to-surface', 'sam ', 'anti-tank missile',
                                      'guided missile')):
            return "Rocket and missile weapons"
        if any(kw in text for kw in ('minigun', 'autocannon', 'howitzer', 'mortar', 'artillery',
                                      'machine gun', 'rifle', 'pistol', 'smg', 'shotgun', 'sniper',
                                      'glock', 'caliber')):
            return "Small arms"
        # Check weapon model prefixes
        weapon_prefixes = ['ak-', 'ar-', 'm4 ', 'm16', 'mg ']
        for prefix in weapon_prefixes:
            if re.search(r'(?:^|[\s(,])' + re.escape(prefix), text):
                return "Small arms"
        # Check for caliber pattern
        if re.search(r'\d[\d.]+x\d+mm|\d[\d.]+mm\b', text):
            return "Small arms"
    
    # Platform classification
    if is_aircraft:
        return "Aircraft"
    
    # UAVs
    if any(kw in text for kw in ('uav', 'drone', 'unmanned aerial', 'mq-', 'rq-', 'predator', 'reaper',
                                  'global hawk', 'heron', 'searcher', 'orbiter')):
        return "UAVs"
    
    # Naval vessels
    # Check for naval keywords, but exclude "tank destroyer" (which contains "destroyer")
    naval_kws = ['ship', 'carrier', 'frigate', 'corvette', 'submarine',
                 'cruiser', 'lhd', 'lha', 'lpd', 'lsv', 'patrol boat', 'mine countermeasures',
                 'amphibious', 'naval', 'vessel class']
    is_naval = any(kw in text for kw in naval_kws)
    # Check for "destroyer" but exclude "tank destroyer"
    if 'destroyer' in text and 'tank destroyer' not in text:
        is_naval = True
    if is_naval:
        return "Naval vessels"
    
    # Armored vehicles and equipment
    if any(kw in text for kw in ('tank', 'main battle tank', 'light tank', 'apc', 'ifv', 'armored',
                                  'armoured', 'mrp', 'btr', 'bmp', 'bradley', 'warrior', 'puma',
                                  'boxer', 'strv', 'leopard', 'tank destroyer', 'self-propelled',
                                  'combat vehicle', 'infantry fighting', 'personnel carrier')):
        return "Armored vehicles and equipment"
    
    # UGVs
    if any(kw in text for kw in ('ugv', 'unmanned ground', 'robot combat', 'talon', 'packbot')):
        return "UGVs"
    
    # Automotive vehicles
    if any(kw in text for kw in ('truck', 'humvee', 'hmmwv', 'jlsv', 'logistics', 'fuel tanker',
                                  'recovery vehicle', 'engineering vehicle')):
        return "Automotive vehicles"
    
    # Weapon classification (fallback for entries without clear Type spec)
    if any(kw in text for kw in ('missile', 'rocket', 'tow', 'stinger', 'javelin', 'hellfire', 'cruise',
                                  'ballistic', 'atgm', 'anti-tank guided', 'surface-to-air', 'air-to-air',
                                  'air-to-surface', 'surface-to-surface', 'sam ', 'anti-tank missile',
                                  'guided missile')):
        return "Rocket and missile weapons"
    if any(kw in text for kw in ('minigun', 'autocannon', 'howitzer', 'mortar', 'artillery',
                                  'machine gun', 'rifle', 'pistol', 'smg', 'shotgun', 'sniper',
                                  'glock', 'caliber')):
        return "Small arms"
    
    return "Aircraft"  # Default fallback
