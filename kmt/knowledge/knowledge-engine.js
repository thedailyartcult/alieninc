/**
 * KMT Consulting Group - Knowledge Base Engine
 * Deep operational intelligence on all Alien.Inc subsidiary companies
 * 
 * Manages:
 * - Subsidiary profiles (strategy, operations, financials, team)
 * - Historical engagement data and outcomes
 * - Market and competitive intelligence
 * - Organizational structure and key personnel
 * - Risk factors and opportunities
 */

class KnowledgeBase {
  constructor() {
    this.subsidiaries = new Map();
    this.marketIntelligence = new Map();
    this.historicalEngagements = new Map();
    this.keyPersonnel = new Map();
    this._initialized = false;
  }

  initialize() {
    if (this._initialized) return this;
    this._loadSubsidiaryData();
    this._loadMarketIntelligence();
    this._initialized = true;
    return this;
  }

  // ─── SUBSIDIARY PROFILES ────────────────────────────────────────

  getSubsidiary(companyId) {
    return this.subsidiaries.get(companyId) || null;
  }

  getAllSubsidiaries() {
    return Array.from(this.subsidiaries.entries()).map(([id, profile]) => ({
      id,
      name: profile.name,
      sector: profile.sector,
      status: profile.status,
      revenue: profile.financials?.annualRevenue || 0,
      employees: profile.headcount || 0,
      lastUpdated: profile.lastUpdated
    }));
  }

  getSubsidiaryFinancials(companyId) {
    const sub = this.subsidiaries.get(companyId);
    if (!sub) return null;
    return {
      revenue: sub.financials.annualRevenue,
      grossMargin: sub.financials.grossMargin,
      operatingMargin: sub.financials.operatingMargin,
      revenueGrowth: sub.financials.revenueGrowth,
      ebitda: sub.financials.ebitda,
      headcount: sub.headcount,
      revenuePerEmployee: sub.headcount > 0 ? sub.financials.annualRevenue / sub.headcount : 0
    };
  }

  getSubsidiaryOperations(companyId) {
    const sub = this.subsidiaries.get(companyId);
    if (!sub) return null;
    return {
      operatingModel: sub.operations.operatingModel,
      keyProcesses: sub.operations.keyProcesses,
      technologyStack: sub.operations.technologyStack,
      vendors: sub.operations.keyVendors,
      painPoints: sub.operations.painPoints,
      maturityLevel: sub.operations.maturityLevel
    };
  }

  getSubsidiaryStrategy(companyId) {
    const sub = this.subsidiaries.get(companyId);
    if (!sub) return null;
    return {
      mission: sub.strategy.mission,
      vision: sub.strategy.vision,
      goals: sub.strategy.strategicGoals,
      moat: sub.strategy.competitiveAdvantage,
      risks: sub.strategy.keyRisks,
      opportunities: sub.strategy.opportunities
    };
  }

  // ─── PERSONNEL INTELLIGENCE ─────────────────────────────────────

  getCompanyPersonnel(companyId) {
    const sub = this.subsidiaries.get(companyId);
    if (!sub) return [];
    return sub.keyPersonnel || [];
  }

  getDecisionMakers(companyId) {
    const personnel = this.getCompanyPersonnel(companyId);
    return personnel.filter(p => 
      ['CEO', 'CTO', 'CFO', 'Managing Partner', 'Managing Director', 'Founder'].includes(p.role)
    );
  }

  getStakeholderMap(companyId) {
    const sub = this.subsidiaries.get(companyId);
    if (!sub) return null;
    return {
      executiveSponsor: sub.stakeholders?.executiveSponsor || null,
      dayToDayContact: sub.stakeholders?.dayToDayContact || null,
      technicalLead: sub.stakeholders?.technicalLead || null,
      financeContact: sub.stakeholders?.financeContact || null
    };
  }

  // ─── MARKET INTELLIGENCE ────────────────────────────────────────

  getMarketIntelligence(companyId) {
    return this.marketIntelligence.get(companyId) || null;
  }

  getCompetitorLandscape(companyId) {
    const intel = this.marketIntelligence.get(companyId);
    if (!intel) return [];
    return intel.competitors || [];
  }

  getMarketSize(companyId) {
    const intel = this.marketIntelligence.get(companyId);
    if (!intel) return null;
    return {
      tam: intel.market.tam,
      sam: intel.market.sam,
      som: intel.market.som,
      growthRate: intel.market.growthRate,
      keyTrends: intel.market.trends
    };
  }

  // ─── ENGAGEMENT HISTORY ─────────────────────────────────────────

  getEngagementHistory(companyId) {
    return this.historicalEngagements.get(companyId) || [];
  }

  addEngagementHistory(companyId, engagement) {
    if (!this.historicalEngagements.has(companyId)) {
      this.historicalEngagements.set(companyId, []);
    }
    this.historicalEngagements.get(companyId).push({
      ...engagement,
      completedDate: new Date().toISOString()
    });
  }

  getCompanyPerformance(companyId) {
    const history = this.getEngagementHistory(companyId);
    if (history.length === 0) return null;

    const totalValue = history.reduce((sum, e) => sum + (e.value || 0), 0);
    const avgCSAT = history.filter(e => e.csat).reduce((sum, e, _, arr) => 
      sum + e.csat / arr.length, 0
    );

    return {
      totalEngagements: history.length,
      totalValue,
      averageCSAT: avgCSAT,
      lastEngagement: history[history.length - 1],
      successRate: history.filter(e => e.outcome === 'successful').length / history.length
    };
  }

  // ─── KNOWLEDGE QUERIES ──────────────────────────────────────────

  searchKnowledge(query) {
    const results = [];
    const queryLower = query.toLowerCase();

    for (const [companyId, profile] of this.subsidiaries) {
      const matches = [];
      
      // Search company name
      if (profile.name.toLowerCase().includes(queryLower)) {
        matches.push({ type: 'company', field: 'name' });
      }

      // Search sector
      if (profile.sector.toLowerCase().includes(queryLower)) {
        matches.push({ type: 'sector', field: 'sector' });
      }

      // Search strategy
      if (profile.strategy?.mission?.toLowerCase().includes(queryLower)) {
        matches.push({ type: 'strategy', field: 'mission' });
      }

      // Search pain points
      if (profile.operations?.painPoints?.some(p => p.toLowerCase().includes(queryLower))) {
        matches.push({ type: 'operations', field: 'painPoints' });
      }

      if (matches.length > 0) {
        results.push({ companyId, profile: profile.name, matches });
      }
    }

    return results;
  }

  getSubsidiarySummary(companyId) {
    const sub = this.subsidiaries.get(companyId);
    if (!sub) return null;

    return {
      id: companyId,
      name: sub.name,
      sector: sub.sector,
      status: sub.status,
      headcount: sub.headcount,
      financials: this.getSubsidiaryFinancials(companyId),
      keyRisks: sub.strategy?.keyRisks?.slice(0, 3) || [],
      topOpportunities: sub.strategy?.opportunities?.slice(0, 3) || [],
      recentEngagements: this.getEngagementHistory(companyId).slice(-3),
      maturityLevel: sub.operations?.maturityLevel || 'unknown'
    };
  }

  // ─── PRIVATE HELPERS ─────────────────────────────────────────────

  _loadSubsidiaryData() {
    // Loads comprehensive subsidiary profiles
    // In production, this reads from subsidiary JSON files
    this.subsidiaries.clear();
  }

  _loadMarketIntelligence() {
    // Loads market data for each subsidiary's sector
    this.marketIntelligence.clear();
  }

  _generateId() {
    return 'KB-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = KnowledgeBase;
}
