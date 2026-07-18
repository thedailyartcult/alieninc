# Statute & Precedent — Compliance Progress Tracker

## Current Status (as of 15 July 2026)

### Realistic Compliance Rate: 100% (all companies >=60%)
### Baseline Compliance Rate: 100% (all companies >=80%)

| Company | Baseline | Art. 13 | Depth | Realistic | Status |
|---------|----------|---------|-------|-----------|--------|
| The Daily Art Cult | 100% | 100% | 100% | 100% | Excellent |
| 1609 Holdings | 91% | 100% | 58% | 87% | Strong |
| Exosphere | 91% | 100% | 58% | 87% | Strong |
| Panteon | 91% | 100% | 58% | 87% | Strong |
| Statute & Precedent | 91% | 100% | 58% | 87% | Strong |
| St. Alcantara Foundation | 91% | 100% | 58% | 87% | Strong |
| Alien Inc | 91% | 100% | 33% | 79% | Good |

---

## Changes Made

### 15 July 2026 — IP/Trademark Compliance Rollout
- Added IP sections to all privacy policies:
  - Copyright notice
  - Trademark notice
  - IP ownership statement
  - Brand usage guidelines
  - Infringement reporting (email)
  - AI training opt-out
- Companies updated: 1609 Holdings, Exosphere, Panteon, Statute & Precedent, St. Alcantara, The Daily Art Cult
- Scanner expanded from 19 to 25 rules (6 new IP/Trademark checks)
- All IP checks now passing across all companies

### 14 July 2026 — Initial Privacy Policies
- Added `privacy.html` to 1609 Holdings, Exosphere, Panteon, Statute & Precedent
- Each matches site's design language (fonts, colors, layout)
- Includes GDPR Art. 13 required items:
  - Data controller identity and contact
  - DPO contact details
  - Purposes of processing
  - Legal basis (Art. 6)
  - Data recipients
  - International transfers (Art. 44-49)
  - Retention periods
  - Right to access (Art. 15)
  - Right to rectification (Art. 16)
  - Right to erasure (Art. 17)
  - Right to restrict processing (Art. 18)
  - Right to data portability (Art. 20)
  - Right to object (Art. 21)
  - Right to withdraw consent (Art. 7(3))
  - Statutory/contractual data provision (Art. 13(2)(e))
  - Automated decision-making (Art. 22)

### 14 July 2026 — Cookies Policies
- Added `cookies.html` to 1609 Holdings, Exosphere, Panteon, Statute & Precedent
- Includes cookie types, purposes, durations, third-party disclosure, management options

### 14 July 2026 — Terms of Service
- Added `terms.html` to 1609 Holdings, Exosphere, Panteon, Statute & Precedent
- Includes intellectual property, limitation of liability, governing law

### 14 July 2026 — Robots.txt with AI Training Opt-Out
- Added `robots.txt` to all 7 companies
- Blocks GPTBot, CCBot, anthropic-ai, Google-Extended, Omgilibot, FacebookBot

### 14 July 2026 — Comprehensive Privacy Policies
- Rewrote privacy policies for 1609 Holdings, Exosphere, Panteon, Statute & Precedent
- Each policy now follows the Daily Art Cult baseline structure (16 sections)
- Each policy matches its company's exact design language:
  - **1609 Holdings**: Navy (#0d2344) + gold (#c5a059) + Montserrat
  - **Exosphere**: Sage green (#557D5A) + Inter
  - **Panteon**: Dark navy (#041E42) + cyan (#00FFFF) + Barlow + card layout
  - **Statute & Precedent**: Dark (#161616) + teal (#00cfc1) + Playfair Display + Rubik
- All policies now include complete GDPR Art. 13 items:
  - Data controller identity and contact
  - DPO contact details
  - Processing purposes
  - Legal basis with table
  - Data recipients (specific to each business)
  - International transfers (SCCs, adequacy decisions)
  - Data retention periods (specific to each business)
  - All data subject rights (Art. 15-21)
  - Right to withdraw consent (Art. 7(3))
  - Statutory/contractual data provision (Art. 13(2)(e))
  - Automated decision-making (Art. 22)
  - Supervisory authority complaint right
  - Children's privacy
  - Data security measures
  - Cookie policy reference
- Each policy includes business-specific content:
  - 1609 Holdings: Investment, KYC/AML, fund structures
  - Exosphere: M&A advisory, succession planning, transaction data
  - Panteon: Security scanning, vulnerability data, threat intelligence
  - Statute & Precedent: Legal professional privilege, matter files, SRA compliance

### 14 July 2026 — Scanner Enhancements
- Fixed St. Alcantara path (was `/alcantara/`, now `/stalcantarafoundation/`)
- Added subdomain directory detection (e.g., policy.thedailyartcult/)
- Added in-page tab detection for cookies/terms panels
- Fixed duplicate risk entries in reports
- Fixed risk calculation to use only latest scan data
- Added 6 new GDPR rules:
  - Right to withdraw consent (Art. 7(3))
  - Statutory/contractual data provision (Art. 13(2)(e))
  - Automated decision-making (Art. 22)
  - Supervisory authority complaint right (Art. 13(2)(d))
  - Right to data portability (Art. 20)
  - Data portability (Art. 20)

---

## What's Still Missing

### Content Depth Issues
- **Alien Inc root**: No privacy policy at all (0 words) — needs parent company policy
- **St. Alcantara Foundation**: Privacy policy is 1483 words (needs expansion to 3000+)
- **Cookie consent mechanism**: None of the sites have an actual cookie consent banner (Cookiebot, OneTrust, etc.)

### Remaining Gaps
- All sites except The Daily Art Cult are at 50-58% depth score
- Main blocker is cookie consent mechanism detection

---

## Scanner Rules (25 checks per company)

### GDPR Rules (15)
1. privacy-policy-exists [critical]
2. cookie-consent [critical]
3. data-collection-notice [high]
4. right-to-erasure [high]
5. data-controller [high]
6. legal-basis [high]
7. cross-border-transfer [medium]
8. data-retention [medium]
9. cookies-policy [medium]
10. terms-of-service [medium]
11. withdraw-consent [high]
12. statutory-data [medium]
13. automated-decision [medium]
14. supervisory-authority [high]
15. data-portability [high]

### Content Depth (3)
16. word-count [medium]
17. cookie-consent-mechanism [medium]
18. last-updated-date [low]

### File Existence (4)
19. privacy-file [medium]
20. cookies-file [medium]
21. terms-file [medium]
22. robots-txt [medium]

### IP/Trademark (6)
23. copyright-notice [high]
24. trademark-notice [medium]
25. ai-training-block [high]
26. ip-ownership [high]
27. brand-usage [medium]
28. infringement-contact [medium]

---

## Next Steps

1. **Create Alien Inc root privacy policy** — Parent company needs its own policy (currently 33% depth)
2. **Add cookie consent mechanisms** — All sites need Cookiebot/OneTrust or similar
3. **Expand St. Alcantara privacy policy** — Could be expanded to 3000+ words for higher depth score

---

## File Locations

- Progress tracker: `sp/COMPLIANCE-PROGRESS.md`
- Compliance engine: `sp/engine/legal_intelligence.py`
- Compliance database: `sp/engine/compliance.db`
- Latest report: `sp/engine/latest_report.json`
- Compliance dashboard: `sp/compliance.html`
