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
| KMT | Centra | 10% |
| KMT | Centra | 10% |
| KMT | Alcantara Art Foundation | 5% (nonprofit) |
| KMT | The Daily Art Cult | 10% |
| KMT | Rousseau Holdings | 15% |
| Rousseau Holdings | KMT | 15% |
| Rousseau Holdings | Panteon | 10% |
| Rousseau Holdings | Centra | 10% |

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
- `kmt/billing/data/invoices.json` - Operating invoice data (10 invoices)

## Financial Data

### YTD Performance (through July 2026)
- **Total Revenue:** $892,000
- **Billed:** $673,300
- **Collected:** $548,800
- **Outstanding:** $124,500

### Revenue by Company
| Company | Revenue |
|---------|---------|
| Panteon | $219,492 |
| Rousseau Holdings | $274,705 |
| Centra | $29,975 |
| Centra | $9,600 |

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
- Reports to **Rousseau Holdings** for portfolio oversight
- Links to **Knowledge Base** for company financial data

## Next Component
→ Methodology Library (consulting frameworks and tools)
