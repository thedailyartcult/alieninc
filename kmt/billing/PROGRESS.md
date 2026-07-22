# KMT Transfer Pricing & Billing System - Progress

**Status:** ✅ Complete
**Completed:** 2026-07-13

## What Was Built

### Rate Card Management
Hourly billing rates by role and seniority:

| Role | Level | Hourly Rate |
|------|-------|-------------|
| Partner | Partner | $350 |
| Partner | Senior | $325 |
| Engagement Manager | Standard | $275 |
| Engagement Manager | Senior | $300 |
| Consultant | Standard | $195 |
| Consultant | Senior | $225 |
| Analyst | Standard | $150 |
| Analyst | Senior | $175 |

### Transfer Pricing Rules
Internal fee structures across the 7 companies:

| From | To | Management Fee Rate |
|------|----|---------------------|
| KMT | Panteon | 12% |
| KMT | Exosphere | 10% |
| KMT | Statute & Precedent | 8% |
| KMT | Alcantara Art Foundation | 5% (nonprofit) |
| KMT | The Daily Art Cult | 10% |
| KMT | 1609 Holdings | 15% |
| 1609 Holdings | KMT | 15% |
| 1609 Holdings | Panteon | 10% |
| 1609 Holdings | Exosphere | 10% |

### Invoice Management
- Generate invoices from approved time entries
- Track invoice status (draft → pending → approved → paid)
- Management fee calculation per transfer pricing rules
- Client-level and service line-level revenue tracking

### Time Tracking
- Log hours by employee, engagement, and date
- Approval workflow for time entries
- Billable vs. non-billable classification
- Employee utilization tracking

### Financial Reporting
- Revenue by company and service line
- Outstanding balances and aging
- Average days to payment
- Utilization metrics by employee

## Files Created
- `kmt/billing/billing-engine.js` - Core billing management engine
- `kmt/billing/data/invoices.json` - Sample invoice data (10 invoices)

## Sample Financial Data

### YTD Performance (through July 2026)
- **Total Revenue:** $892,000
- **Billed:** $673,300
- **Collected:** $548,800
- **Outstanding:** $124,500

### Revenue by Company
| Company | Revenue |
|---------|---------|
| Panteon | $219,492 |
| 1609 Holdings | $274,705 |
| Exosphere | $29,975 |
| Statute & Precedent | $3,888 |

### Revenue by Service Line
| Service Line | Revenue |
|--------------|---------|
| Operating Model & Performance Improvement | $219,492 |
| Strategy & Market Entry | $330,705 |
| Applied AI Workflow Transformation | $3,888 |
| Management Fees | $338,400 |

## Integration Points
- Feeds **Engagement Management** with budget tracking
- Powers **Performance Dashboard** with financial metrics
- Reports to **1609 Holdings** for portfolio oversight
- Links to **Knowledge Base** for company financial data

## Next Component
→ Methodology Library (consulting frameworks and tools)
