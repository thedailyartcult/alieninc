/**
 * KMT Consulting Group - Core Engine
 * 
 * Main orchestrator that:
 * 1. Takes a query about a company
 * 2. Loads relevant data from ecosystem
 * 3. Runs analysis through appropriate frameworks
 * 4. Generates recommendations
 * 5. Returns structured consulting output
 */

const fs = require('fs');
const path = require('path');
const FinancialAnalysis = require('../analysis/financial-analysis');
const OperationalAnalysis = require('../analysis/operational-analysis');
const RecommendationEngine = require('./recommendation-engine');

class KMTEngine {
  constructor() {
    this.ecosystemData = null;
    this.financialAnalysis = null;
    this.operationalAnalysis = null;
    this.recommendationEngine = new RecommendationEngine();
    this._initialized = false;
  }

  /**
   * Initialize the engine with ecosystem data
   * @param {string} dataPath - Path to ecosystem JSON file
   */
  initialize(dataPath) {
    if (this._initialized) return this;
    
    // Load ecosystem data
    const fullPath = dataPath || path.join(__dirname, '../../data/alieninc-ecosystem.json');
    this.ecosystemData = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
    
    // Initialize analysis engines
    this.financialAnalysis = new FinancialAnalysis(this.ecosystemData);
    this.operationalAnalysis = new OperationalAnalysis(this.ecosystemData);
    
    this._initialized = true;
    return this;
  }

  /**
   * Analyze a company and provide consulting output
   * @param {string} companyId - Company ID (panteon, kmt, etc.)
   * @param {Object} options - Analysis options
   * @returns {Object} Comprehensive consulting output
   */
  analyze(companyId, options = {}) {
    if (!this._initialized) {
      return { error: 'Engine not initialized. Call initialize() first.' };
    }

    const company = this.ecosystemData.companies.find(c => c.id === companyId);
    if (!company) {
      return { error: `Company ${companyId} not found. Available: ${this.ecosystemData.companies.map(c => c.id).join(', ')}` };
    }

    // Run analyses
    const analyses = {
      financial: this.financialAnalysis.analyze(companyId),
      operational: this.operationalAnalysis.analyze(companyId),
      strategic: this._runStrategicAnalysis(companyId),
      competitive: this._runCompetitiveAnalysis(companyId)
    };

    // Generate recommendations
    const recommendations = this.recommendationEngine.generateRecommendations(analyses);

    // Generate health scores
    const healthScores = {
      financial: this.financialAnalysis.getHealthScore(companyId),
      operational: this.operationalAnalysis.getHealthScore(companyId)
    };
    healthScores.overall = Math.round((healthScores.financial + healthScores.operational) / 2);

    // Get company context
    const companyContext = this._getCompanyContext(companyId);

    // Get portfolio context
    const portfolioContext = this._getPortfolioContext(companyId);

    return {
      // Metadata
      queryType: 'company_analysis',
      companyId,
      companyName: company.brandName,
      analysisDate: new Date().toISOString(),
      
      // Executive Summary
      executiveSummary: this._generateExecutiveSummary(company, analyses, recommendations, healthScores),
      
      // Health Scores
      healthScores,
      
      // Detailed Analyses
      analyses,
      
      // Recommendations
      recommendations,
      
      // Context
      companyContext,
      portfolioContext
    };
  }

  /**
   * Get company overview
   */
  getCompanyOverview(companyId) {
    const company = this.ecosystemData.companies.find(c => c.id === companyId);
    if (!company) return { error: `Company ${companyId} not found` };

    return {
      id: company.id,
      name: company.brandName,
      legalName: company.legalName,
      category: company.category,
      yearFounded: company.yearFounded,
      ownership: company.ownershipStatus,
      mission: company.mission,
      vision: company.vision,
      headcount: company.headcount,
      leadership: company.leadershipTeam,
      serviceOfferings: company.serviceOfferings,
      financials: this._getLatestFinancials(company),
      kpis: company.kpis2026F
    };
  }

  /**
   * Get portfolio overview (all companies)
   */
  getPortfolioOverview() {
    return this.ecosystemData.companies.map(company => ({
      id: company.id,
      name: company.brandName,
      category: company.category,
      revenue: this._getLatestFinancials(company).revenue,
      headcount: company.headcount?.['2026F'] || 0,
      healthScore: this.financialAnalysis.getHealthScore(company.id)
    }));
  }

  /**
   * Get cross-company insights
   */
  getCrossCompanyInsights() {
    const insights = [];
    
    // Revenue distribution
    const companies = this.ecosystemData.companies;
    const totalRevenue = companies.reduce((sum, c) => 
      sum + (c.annualFinancials?.[c.annualFinancials.length - 1]?.revenue || 0), 0
    );
    
    insights.push({
      type: 'portfolio_composition',
      insight: `Portfolio total revenue: $${(totalRevenue / 1000000).toFixed(1)}M across ${companies.length} companies`,
      companies: companies.map(c => ({
        name: c.brandName,
        revenue: c.annualFinancials?.[c.annualFinancials.length - 1]?.revenue || 0,
        share: ((c.annualFinancials?.[c.annualFinancials.length - 1]?.revenue || 0) / totalRevenue * 100).toFixed(1) + '%'
      }))
    });
    
    // Intercompany transactions
    const transactions = this.ecosystemData.intercompanyTransactions2026F || [];
    const intercompanyVolume = transactions.reduce((sum, t) => sum + (t.amount || 0), 0);
    
    insights.push({
      type: 'intercompany_dependencies',
      insight: `$${(intercompanyVolume / 1000).toFixed(0)}K in intercompany transactions across ${transactions.length} relationships`,
      topFlows: transactions
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 3)
        .map(t => ({
          from: t.fromCompanyId,
          to: t.toCompanyId,
          amount: t.amount,
          description: t.description
        }))
    });
    
    return insights;
  }

  // ─── PRIVATE METHODS ──────────────────────────────────────────

  _runStrategicAnalysis(companyId) {
    const company = this.ecosystemData.companies.find(c => c.id === companyId);
    if (!company) return null;

    const kpis = company.kpis2026F || {};
    const financials = company.annualFinancials || [];
    const latest = financials[financials.length - 1] || {};

    const findings = [];
    const recommendations = [];

    // Market position analysis
    findings.push({
      type: 'market_position',
      finding: `${company.brandName} operates in ${company.category} with ${company.headcount?.['2026F'] || 0} employees`,
      impact: 'info'
    });

    // Growth trajectory
    if (financials.length >= 2) {
      const prev = financials[financials.length - 2];
      const growth = (latest.revenue - prev.revenue) / prev.revenue;
      if (growth > 0.2) {
        findings.push({
          type: 'growth',
          finding: `Strong revenue growth of ${(growth * 100).toFixed(1)}% YoY`,
          impact: 'positive'
        });
      }
    }

    // Service line concentration
    const revenueBreakdown = company.revenueBreakdown2026F || [];
    if (revenueBreakdown.length > 0) {
      const topService = revenueBreakdown.reduce((max, item) => item.share > (max?.share || 0) ? item : max, null);
      if (topService && topService.share > 0.6) {
        findings.push({
          type: 'concentration',
          finding: `High concentration in ${topService.serviceLineId} (${(topService.share * 100).toFixed(0)}% of revenue)`,
          impact: 'risk'
        });
        recommendations.push({
          area: 'strategy',
          priority: 'medium',
          recommendation: 'Diversify revenue streams to reduce concentration risk',
          expectedImpact: 'Reduced vulnerability to market shifts',
          effort: 'high',
          timeframe: '12+ months'
        });
      }
    }

    return {
      findings,
      recommendations,
      strategicPosition: {
        category: company.category,
        competitiveAdvantage: company.mission,
        growthStage: this._assessGrowthStage(company)
      }
    };
  }

  _runCompetitiveAnalysis(companyId) {
    const company = this.ecosystemData.companies.find(c => c.id === companyId);
    if (!company) return null;

    const peers = this.ecosystemData.companies
      .filter(c => c.id !== companyId && c.category !== 'Holding company')
      .map(c => ({
        id: c.id,
        name: c.brandName,
        category: c.category,
        revenue: c.annualFinancials?.[c.annualFinancials.length - 1]?.revenue || 0,
        headcount: c.headcount?.['2026F'] || 0
      }));

    const companyRevenue = company.annualFinancials?.[company.annualFinancials.length - 1]?.revenue || 0;
    
    // Find direct competitors (same category)
    const directCompetitors = peers.filter(p => 
      p.category.toLowerCase().includes(company.category.toLowerCase().split(' ')[0])
    );

    // Find comparable companies (similar size)
    const sizeRange = [companyRevenue * 0.5, companyRevenue * 2];
    const comparableCompanies = peers.filter(p => 
      p.revenue >= sizeRange[0] && p.revenue <= sizeRange[1]
    );

    const findings = [];
    const recommendations = [];

    if (directCompetitors.length > 0) {
      findings.push({
        type: 'direct_competition',
        finding: `${directCompetitors.length} direct competitor(s) identified in portfolio`,
        competitors: directCompetitors.map(c => c.name),
        impact: 'info'
      });
    }

    if (comparableCompanies.length > 0) {
      const avgPeerRevenue = comparableCompanies.reduce((sum, c) => sum + c.revenue, 0) / comparableCompanies.length;
      const revenuePosition = companyRevenue > avgPeerRevenue ? 'above_average' : 'below_average';
      
      findings.push({
        type: 'competitive_position',
        finding: `Revenue is ${revenuePosition} compared to ${comparableCompanies.length} peer(s) of similar size`,
        impact: revenuePosition === 'above_average' ? 'positive' : 'attention_needed'
      });
    }

    return {
      findings,
      recommendations,
      competitiveLandscape: {
        directCompetitors,
        comparableCompanies,
        uniquePosition: company.category
      }
    };
  }

  _getCompanyContext(companyId) {
    const company = this.ecosystemData.companies.find(c => c.id === companyId);
    if (!company) return null;

    // Get intercompany relationships
    const transactions = this.ecosystemData.intercompanyTransactions2026F || [];
    const incoming = transactions.filter(t => t.toCompanyId === companyId);
    const outgoing = transactions.filter(t => t.fromCompanyId === companyId);

    return {
      company,
      incomingTransactions: incoming,
      outgoingTransactions: outgoing,
      dependencies: incoming.map(t => t.fromCompanyId),
      dependents: outgoing.map(t => t.toCompanyId)
    };
  }

  _getPortfolioContext(companyId) {
    const company = this.ecosystemData.companies.find(c => c.id === companyId);
    const allCompanies = this.ecosystemData.companies;
    
    // Calculate portfolio metrics
    const totalRevenue = allCompanies.reduce((sum, c) => 
      sum + (c.annualFinancials?.[c.annualFinancials.length - 1]?.revenue || 0), 0
    );
    const companyRevenue = company?.annualFinancials?.[company.annualFinancials.length - 1]?.revenue || 0;
    
    return {
      portfolioSize: allCompanies.length,
      portfolioRevenue: totalRevenue,
      companyShare: totalRevenue > 0 ? (companyRevenue / totalRevenue * 100).toFixed(1) + '%' : '0%',
      holdingCompany: allCompanies.find(c => c.id === '1609'),
      roleInPortfolio: this._assessPortfolioRole(company)
    };
  }

  _assessGrowthStage(company) {
    const financials = company.annualFinancials || [];
    if (financials.length < 2) return 'early_stage';
    
    const recent = financials.slice(-2);
    const growth = (recent[1].revenue - recent[0].revenue) / recent[0].revenue;
    
    if (growth > 0.3) return 'hyper_growth';
    if (growth > 0.15) return 'high_growth';
    if (growth > 0.05) return 'growth';
    if (growth > 0) return 'mature';
    return 'declining';
  }

  _assessPortfolioRole(company) {
    if (!company) return null;
    
    const role = {
      primary: company.category,
      contributions: []
    };
    
    // Identify contributions based on category and services
    if (company.id === '1609') {
      role.contributions = ['Capital allocation', 'Governance', 'Strategic oversight'];
    } else if (company.id === 'kmt') {
      role.contributions = ['Strategy consulting', 'Operational improvement', 'AI transformation'];
    } else if (company.id === 'panteon') {
      role.contributions = ['Cybersecurity', 'Risk management', 'Diligence support'];
    } else if (company.id === 'exosphere') {
      role.contributions = ['Acquisition sourcing', 'Succession advisory', 'Deal execution'];
    } else if (company.id === 'statute') {
      role.contributions = ['Legal services', 'Contract operations', 'AI policy'];
    } else if (company.id === 'tdac') {
      role.contributions = ['Media distribution', 'Content creation', 'Audience building'];
    } else if (company.id === 'alcantara') {
      role.contributions = ['Cultural preservation', 'Public benefit', 'Education'];
    }
    
    return role;
  }

  _getLatestFinancials(company) {
    const financials = company.annualFinancials || [];
    const latest = financials[financials.length - 1] || {};
    
    return {
      year: latest.year,
      revenue: latest.revenue || 0,
      operatingCosts: latest.operatingCosts || 0,
      ebitda: latest.ebitda || 0,
      cashEnding: latest.cashEnding || 0,
      margin: latest.revenue > 0 ? (latest.revenue - latest.operatingCosts) / latest.revenue : 0
    };
  }

  _generateExecutiveSummary(company, analyses, recommendations, healthScores) {
    const financial = analyses.financial;
    const operational = analyses.operational;
    
    const keyFindings = [];
    
    // Financial findings
    if (financial?.findings) {
      financial.findings.forEach(f => keyFindings.push(f));
    }
    
    // Operational findings
    if (operational?.findings) {
      operational.findings.forEach(f => keyFindings.push(f));
    }
    
    // Top recommendations
    const topRecs = recommendations.prioritized.slice(0, 3);
    
    return {
      companyName: company.brandName,
      healthScore: healthScores.overall,
      healthRating: healthScores.overall >= 70 ? 'Strong' : 
                    healthScores.overall >= 50 ? 'Developing' : 'Needs Attention',
      keyFindings: keyFindings.slice(0, 5),
      topRecommendations: topRecs.map(r => ({
        rank: r.rank,
        recommendation: r.recommendation,
        priority: r.priority,
        timeframe: r.timeframe
      })),
      overallAssessment: this._generateOverallAssessment(company, healthScores, recommendations)
    };
  }

  _generateOverallAssessment(company, healthScores, recommendations) {
    const score = healthScores.overall;
    const criticalCount = recommendations.summary.byPriority.critical || 0;
    const highCount = recommendations.summary.byPriority.high || 0;
    
    if (score >= 70 && criticalCount === 0) {
      return `${company.brandName} is performing well with a health score of ${score}/100. Focus on optimization and growth.`;
    } else if (score >= 50) {
      return `${company.brandName} has a health score of ${score}/100 with ${criticalCount + highCount} priority items to address. Focus on operational improvements.`;
    } else {
      return `${company.brandName} needs attention with a health score of ${score}/100. ${criticalCount} critical and ${highCount} high-priority issues require immediate action.`;
    }
  }
}

module.exports = KMTEngine;
