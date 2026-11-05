/**
 * KMT Consulting Group - Recommendation Engine
 * 
 * Takes analysis outputs and generates:
 * - Prioritized recommendations (by impact and feasibility)
 * - Implementation roadmaps (quick wins → medium term → long term)
 * - Resource requirements
 * - Success metrics
 */

class RecommendationEngine {
  constructor() {
    this.impactLevels = ['critical', 'high', 'medium', 'low'];
    this.effortLevels = ['low', 'medium', 'high'];
    this.timeframes = ['immediate', '1-3 months', '3-6 months', '6-12 months', '12+ months'];
  }

  /**
   * Generate prioritized recommendations from multiple analysis outputs
   * @param {Object} analyses - Object containing analysis results
   * @returns {Object} Prioritized recommendations with roadmap
   */
  generateRecommendations(analyses) {
    const allRecommendations = [];
    
    // Collect recommendations from all analyses
    if (analyses.financial?.recommendations) {
      allRecommendations.push(...analyses.financial.recommendations.map(r => ({
        ...r, source: 'financial_analysis'
      })));
    }
    
    if (analyses.operational?.recommendations) {
      allRecommendations.push(...analyses.operational.recommendations.map(r => ({
        ...r, source: 'operational_analysis'
      })));
    }
    
    if (analyses.strategic?.recommendations) {
      allRecommendations.push(...analyses.strategic.recommendations.map(r => ({
        ...r, source: 'strategic_analysis'
      })));
    }
    
    if (analyses.competitive?.recommendations) {
      allRecommendations.push(...analyses.competitive.recommendations.map(r => ({
        ...r, source: 'competitive_analysis'
      })));
    }
    
    // Deduplicate and merge similar recommendations
    const merged = this._mergeRecommendations(allRecommendations);
    
    // Prioritize
    const prioritized = this._prioritizeRecommendations(merged);
    
    // Generate roadmap
    const roadmap = this._generateRoadmap(prioritized);
    
    // Calculate summary metrics
    const summary = this._calculateSummary(prioritized);
    
    return {
      totalRecommendations: prioritized.length,
      summary,
      prioritized,
      roadmap,
      quickWins: prioritized.filter(r => r.timeframe === 'immediate' || r.timeframe === '1-3 months'),
      mediumTerm: prioritized.filter(r => r.timeframe === '3-6 months'),
      longTerm: prioritized.filter(r => r.timeframe === '6-12 months' || r.timeframe === '12+ months')
    };
  }

  /**
   * Score a recommendation (0-100) based on impact and effort
   */
  scoreRecommendation(recommendation) {
    const impactScores = { critical: 25, high: 20, medium: 15, low: 10 };
    const effortScores = { low: 25, medium: 15, high: 5 };
    
    const impactScore = impactScores[recommendation.priority] || 10;
    const effortScore = effortScores[recommendation.effort] || 10;
    
    // Bonus for quick wins (low effort, high impact)
    let quickWinBonus = 0;
    if (recommendation.effort === 'low' && (recommendation.priority === 'critical' || recommendation.priority === 'high')) {
      quickWinBonus = 10;
    }
    
    return impactScore + effortScore + quickWinBonus;
  }

  /**
   * Generate implementation plan for a single recommendation
   */
  generateImplementationPlan(recommendation) {
    const plan = {
      recommendation: recommendation.recommendation,
      area: recommendation.area,
      priority: recommendation.priority,
      
      // Phased implementation
      phases: [],
      
      // Resource requirements
      resources: this._estimateResources(recommendation),
      
      // Success metrics
      successMetrics: this._defineSuccessMetrics(recommendation),
      
      // Risks and mitigations
      risks: this._identifyRisks(recommendation),
      
      // Dependencies
      dependencies: this._identifyDependencies(recommendation)
    };
    
    // Generate phases based on timeframe
    if (recommendation.timeframe === 'immediate') {
      plan.phases = [
        { name: 'Assessment', duration: '1 week', activities: ['Validate recommendation scope', 'Identify stakeholders'] },
        { name: 'Execution', duration: '1-2 weeks', activities: ['Implement changes', 'Monitor progress'] },
        { name: 'Review', duration: '1 week', activities: ['Measure impact', 'Document learnings'] }
      ];
    } else if (recommendation.timeframe === '1-3 months') {
      plan.phases = [
        { name: 'Planning', duration: '2 weeks', activities: ['Detailed assessment', 'Stakeholder alignment', 'Resource allocation'] },
        { name: 'Pilot', duration: '4-6 weeks', activities: ['Test approach', 'Iterate based on feedback'] },
        { name: 'Scale', duration: '4-6 weeks', activities: ['Roll out broadly', 'Monitor and optimize'] }
      ];
    } else if (recommendation.timeframe === '3-6 months') {
      plan.phases = [
        { name: 'Discovery', duration: '3-4 weeks', activities: ['Deep dive analysis', 'Option development', 'Business case'] },
        { name: 'Design', duration: '4-6 weeks', activities: ['Solution design', 'Stakeholder review', 'Finalize approach'] },
        { name: 'Implementation', duration: '8-12 weeks', activities: ['Phased rollout', 'Change management', 'Performance tracking'] }
      ];
    } else {
      plan.phases = [
        { name: 'Strategy', duration: '4-6 weeks', activities: ['Strategic assessment', 'Market analysis', 'Roadmap development'] },
        { name: 'Foundation', duration: '8-12 weeks', activities: ['Build capabilities', 'Establish processes', 'Quick wins'] },
        { name: 'Execution', duration: '12-24 weeks', activities: ['Full implementation', 'Scale operations', 'Continuous improvement'] }
      ];
    }
    
    return plan;
  }

  // ─── PRIVATE METHODS ──────────────────────────────────────────

  _mergeRecommendations(recommendations) {
    const merged = [];
    const seen = new Map();
    
    for (const rec of recommendations) {
      const key = `${rec.area}-${rec.recommendation}`;
      if (seen.has(key)) {
        // Merge: keep the higher priority
        const existing = seen.get(key);
        if (this.impactLevels.indexOf(rec.priority) < this.impactLevels.indexOf(existing.priority)) {
          existing.priority = rec.priority;
        }
        existing.sources.push(rec.source);
      } else {
        merged.push({
          ...rec,
          sources: [rec.source],
          id: this._generateId()
        });
        seen.set(key, merged[merged.length - 1]);
      }
    }
    
    return merged;
  }

  _prioritizeRecommendations(recommendations) {
    // Score each recommendation
    const scored = recommendations.map(rec => ({
      ...rec,
      score: this.scoreRecommendation(rec)
    }));
    
    // Sort by score (highest first)
    scored.sort((a, b) => b.score - a.score);
    
    // Assign rank
    return scored.map((rec, index) => ({
      ...rec,
      rank: index + 1
    }));
  }

  _generateRoadmap(prioritized) {
    const roadmap = {
      immediate: [],
      shortTerm: [],
      mediumTerm: [],
      longTerm: []
    };
    
    for (const rec of prioritized) {
      if (rec.timeframe === 'immediate') {
        roadmap.immediate.push(rec);
      } else if (rec.timeframe === '1-3 months') {
        roadmap.shortTerm.push(rec);
      } else if (rec.timeframe === '3-6 months') {
        roadmap.mediumTerm.push(rec);
      } else {
        roadmap.longTerm.push(rec);
      }
    }
    
    return roadmap;
  }

  _calculateSummary(prioritized) {
    const byPriority = {
      critical: prioritized.filter(r => r.priority === 'critical').length,
      high: prioritized.filter(r => r.priority === 'high').length,
      medium: prioritized.filter(r => r.priority === 'medium').length,
      low: prioritized.filter(r => r.priority === 'low').length
    };
    
    const byArea = {};
    for (const rec of prioritized) {
      byArea[rec.area] = (byArea[rec.area] || 0) + 1;
    }
    
    const avgScore = prioritized.reduce((sum, r) => sum + r.score, 0) / prioritized.length;
    
    return {
      total: prioritized.length,
      byPriority,
      byArea,
      averageScore: Math.round(avgScore),
      quickWinsCount: prioritized.filter(r => 
        r.effort === 'low' && (r.priority === 'critical' || r.priority === 'high')
      ).length
    };
  }

  _estimateResources(recommendation) {
    const baseResources = {
      low: { hours: 20, people: 1, cost: 5000 },
      medium: { hours: 80, people: 2, cost: 20000 },
      high: { hours: 200, people: 3, cost: 50000 }
    };
    
    return baseResources[recommendation.effort] || baseResources.medium;
  }

  _defineSuccessMetrics(recommendation) {
    const metricsByArea = {
      operations: ['Margin improvement', 'Cost reduction', 'Process efficiency'],
      productivity: ['Utilization rate', 'Revenue per employee', 'Delivery capacity'],
      finance: ['Cash runway', 'EBITDA margin', 'Revenue growth'],
      strategy: ['Market share', 'Revenue diversification', 'Competitive position'],
      client_retention: ['Retention rate', 'Client satisfaction', 'Renewal rate'],
      client_diversification: ['Client count', 'Industry coverage', 'Concentration risk'],
      business_development: ['Win rate', 'Pipeline value', 'Proposal quality'],
      client_economics: ['LTV/CAC ratio', 'CAC payback period', 'Client profitability'],
      delivery: ['On-time delivery', 'On-budget delivery', 'Client satisfaction']
    };
    
    return metricsByArea[recommendation.area] || ['Recommendation implemented', 'Stakeholder satisfaction'];
  }

  _identifyRisks(recommendation) {
    return [
      { risk: 'Resource constraints may delay implementation', likelihood: 'medium', mitigation: 'Secure stakeholder commitment early' },
      { risk: 'Organizational resistance to change', likelihood: 'medium', mitigation: 'Invest in change management and communication' }
    ];
  }

  _identifyDependencies(recommendation) {
    const deps = [];
    
    if (recommendation.area === 'client_retention') {
      deps.push('Client relationship data', 'Renewal timeline visibility');
    }
    
    if (recommendation.area === 'operations') {
      deps.push('Process documentation', 'Performance baseline data');
    }
    
    if (recommendation.area === 'finance') {
      deps.push('Financial reporting', 'Budget authority');
    }
    
    return deps;
  }

  _generateId() {
    return 'REC-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

module.exports = RecommendationEngine;
