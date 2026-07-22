/**
 * KMT Consulting Group - Transfer Pricing & Billing System
 * Tracks internal fees across the Alien Inc. portfolio
 * 
 * Manages:
 * - Hourly billing rates by role and seniority
 * - Engagement-level fee tracking
 * - Internal transfer pricing between companies
 * - Cost allocation and profitability analysis
 * - Rousseau oversight and reporting
 */

class BillingSystem {
  constructor() {
    this.rateCards = new Map();
    this.invoices = new Map();
    this.timeEntries = new Map();
    this.transferPricing = new Map();
    this._initialized = false;
  }

  initialize() {
    if (this._initialized) return this;
    this._loadRateCards();
    this._loadTransferPricingRules();
    this._initialized = true;
    return this;
  }

  // ─── RATE MANAGEMENT ────────────────────────────────────────────

  getRateCard(role, seniority) {
    const key = `${role}-${seniority}`;
    return this.rateCards.get(key) || this._getDefaultRate(role);
  }

  getRateCardByRole(role) {
    const rates = [];
    for (const [key, rate] of this.rateCards) {
      if (key.startsWith(role)) {
        rates.push(rate);
      }
    }
    return rates;
  }

  getAllRateCards() {
    return Array.from(this.rateCards.entries()).map(([key, rate]) => ({
      key,
      ...rate
    }));
  }

  calculateEngagementRate(engagement) {
    if (!engagement.assignedTeam || engagement.assignedTeam.length === 0) {
      return { blendedRate: 0, totalCost: 0 };
    }

    let totalHours = 0;
    let totalCost = 0;

    for (const member of engagement.assignedTeam) {
      const hours = engagement.metrics?.hoursBudgeted || 100;
      const rate = member.hourlyRate || this.getRateCard(member.role, 'standard').rate;
      totalHours += hours;
      totalCost += hours * rate;
    }

    return {
      blendedRate: totalHours > 0 ? totalCost / totalHours : 0,
      totalCost,
      totalHours
    };
  }

  // ─── TIME TRACKING ──────────────────────────────────────────────

  logTime(entry) {
    const timeEntry = {
      id: this._generateId(),
      engagementId: entry.engagementId,
      employee: entry.employee,
      date: entry.date || new Date().toISOString(),
      hours: entry.hours,
      description: entry.description,
      billable: entry.billable !== false,
      rate: entry.rate || this._getEmployeeRate(entry.employee),
      status: 'logged'
    };

    timeEntry.amount = timeEntry.hours * timeEntry.rate;
    this.timeEntries.set(timeEntry.id, timeEntry);
    return timeEntry;
  }

  approveTimeEntry(timeEntryId) {
    const entry = this.timeEntries.get(timeEntryId);
    if (!entry) return { error: 'Time entry not found' };
    entry.status = 'approved';
    return entry;
  }

  getTimeEntriesByEngagement(engagementId) {
    const entries = [];
    for (const [id, entry] of this.timeEntries) {
      if (entry.engagementId === engagementId) {
        entries.push(entry);
      }
    }
    return entries;
  }

  getTimeEntriesByEmployee(employee, startDate, endDate) {
    const entries = [];
    for (const [id, entry] of this.timeEntries) {
      if (entry.employee === employee) {
        const entryDate = new Date(entry.date);
        if (entryDate >= new Date(startDate) && entryDate <= new Date(endDate)) {
          entries.push(entry);
        }
      }
    }
    return entries;
  }

  // ─── INVOICING ──────────────────────────────────────────────────

  generateInvoice(engagementId, period) {
    const entries = this.getTimeEntriesByEngagement(engagementId);
    const periodEntries = entries.filter(e => {
      const entryDate = new Date(e.date);
      return entryDate >= new Date(period.start) && 
             entryDate <= new Date(period.end) &&
             e.status === 'approved';
    });

    const invoice = {
      id: this._generateId(),
      engagementId,
      period,
      generatedDate: new Date().toISOString(),
      lineItems: periodEntries.map(e => ({
        date: e.date,
        employee: e.employee,
        hours: e.hours,
        rate: e.rate,
        amount: e.amount,
        description: e.description
      })),
      subtotal: periodEntries.reduce((sum, e) => sum + e.amount, 0),
      tax: 0,
      total: 0,
      status: 'draft'
    };

    invoice.total = invoice.subtotal + invoice.tax;
    this.invoices.set(invoice.id, invoice);
    return invoice;
  }

  approveInvoice(invoiceId) {
    const invoice = this.invoices.get(invoiceId);
    if (!invoice) return { error: 'Invoice not found' };
    invoice.status = 'approved';
    invoice.approvedDate = new Date().toISOString();
    return invoice;
  }

  getInvoicesByClient(clientCompany) {
    const results = [];
    for (const [id, invoice] of this.invoices) {
      if (invoice.clientCompany === clientCompany) {
        results.push(invoice);
      }
    }
    return results;
  }

  // ─── TRANSFER PRICING ───────────────────────────────────────────

  calculateTransferFee(fromCompany, toCompany, serviceType, amount) {
    const rule = this.transferPricing.get(`${fromCompany}-${toCompany}`);
    if (!rule) {
      // Default: 10% management fee
      return {
        baseAmount: amount,
        managementFee: amount * 0.10,
        totalFee: amount * 1.10
      };
    }

    return {
      baseAmount: amount,
      managementFee: amount * rule.managementFeeRate,
      totalFee: amount * (1 + rule.managementFeeRate),
      rule: rule.name
    };
  }

  getTransferPricingMatrix() {
    const matrix = {};
    for (const [key, rule] of this.transferPricing) {
      const [from, to] = key.split('-');
      if (!matrix[from]) matrix[from] = {};
      matrix[from][to] = {
        managementFeeRate: rule.managementFeeRate,
        description: rule.description
      };
    }
    return matrix;
  }

  // ─── FINANCIAL REPORTING ────────────────────────────────────────

  getRevenueByCompany(companyId) {
    let totalRevenue = 0;
    for (const [id, invoice] of this.invoices) {
      if (invoice.clientCompany === companyId && invoice.status === 'approved') {
        totalRevenue += invoice.total;
      }
    }
    return totalRevenue;
  }

  getRevenueByServiceLine(serviceLine) {
    let totalRevenue = 0;
    let count = 0;
    for (const [id, invoice] of this.invoices) {
      if (invoice.serviceLine === serviceLine && invoice.status === 'approved') {
        totalRevenue += invoice.total;
        count++;
      }
    }
    return { totalRevenue, count };
  }

  getUtilizationMetrics(employee) {
    const entries = this.getTimeEntriesByEmployee(
      employee, 
      this._getMonthStart(), 
      this._getMonthEnd()
    );

    const billableHours = entries.filter(e => e.billable).reduce((sum, e) => sum + e.hours, 0);
    const totalHours = entries.reduce((sum, e) => sum + e.hours, 0);
    const targetHours = 160; // Standard monthly target

    return {
      billableHours,
      totalHours,
      utilization: billableHours / targetHours,
      revenue: entries.filter(e => e.billable).reduce((sum, e) => sum + e.amount, 0)
    };
  }

  // ─── PRIVATE HELPERS ─────────────────────────────────────────────

  _loadRateCards() {
    const defaultRates = [
      { role: 'Partner', seniority: 'partner', rate: 350, description: 'Partner-level consulting' },
      { role: 'Partner', seniority: 'senior', rate: 325, description: 'Senior Partner' },
      { role: 'Engagement Manager', seniority: 'standard', rate: 275, description: 'EM-level delivery' },
      { role: 'Engagement Manager', seniority: 'senior', rate: 300, description: 'Senior EM' },
      { role: 'Consultant', seniority: 'standard', rate: 195, description: 'Consultant-level work' },
      { role: 'Consultant', seniority: 'senior', rate: 225, description: 'Senior Consultant' },
      { role: 'Analyst', seniority: 'standard', rate: 150, description: 'Analyst-level support' },
      { role: 'Analyst', seniority: 'senior', rate: 175, description: 'Senior Analyst' }
    ];

    defaultRates.forEach(rate => {
      this.rateCards.set(`${rate.role}-${rate.seniority}`, rate);
    });
  }

  _loadTransferPricingRules() {
    const rules = [
      { from: 'kmt', to: 'panteon', managementFeeRate: 0.12, description: 'KMT to Panteon - Standard consulting rate' },
      { from: 'kmt', to: 'centra', managementFeeRate: 0.10, description: 'KMT to Centra - Cybersecurity services rate' },
      { from: 'kmt', to: 'statute', managementFeeRate: 0.08, description: 'KMT to Statute - Legal services rate' },
      { from: 'kmt', to: 'alcantaraartfoundation', managementFeeRate: 0.05, description: 'KMT to Alcantara Art Foundation - Nonprofit rate' },
      { from: 'kmt', to: 'thedailyartcult', managementFeeRate: 0.10, description: 'KMT to TDAC - Standard rate' },
      { from: 'kmt', to: 'rousseau', managementFeeRate: 0.15, description: 'KMT to Rousseau - Holdco oversight rate' },
      { from: 'rousseau', to: 'kmt', managementFeeRate: 0.15, description: 'Rousseau to KMT - Management fee' },
      { from: 'rousseau', to: 'panteon', managementFeeRate: 0.10, description: 'Rousseau to Panteon - Portfolio oversight' },
      { from: 'rousseau', to: 'centra', managementFeeRate: 0.10, description: 'Rousseau to Centra - Portfolio oversight' }
    ];

    rules.forEach(rule => {
      this.transferPricing.set(`${rule.from}-${rule.to}`, rule);
    });
  }

  _getDefaultRate(role) {
    const defaultRates = {
      'Partner': 350,
      'Engagement Manager': 275,
      'Consultant': 195,
      'Analyst': 150
    };
    return { rate: defaultRates[role] || 200 };
  }

  _getEmployeeRate(employee) {
    // In production, looks up employee rate from HR system
    return 235; // Average KMT rate
  }

  _getMonthStart() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
  }

  _getMonthEnd() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString();
  }

  _generateId() {
    return 'INV-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BillingSystem;
}
