/**
 * KMT Consulting Group - Financial Analysis Engine
 * 
 * Processes company financial data to generate insights:
 * - Revenue analysis (growth, composition, trajectory)
 * - Margin analysis (gross, operating, trends)
 * - Cash flow analysis (runway, burn rate)
 * - Peer comparison (across Alien.Inc portfolio)
 * - Investment thesis evaluation
 */

const fs = require('fs');
const path = require('path');

class FinancialAnalysis {
  constructor(ecosystemData) {
    this.data = ecosystemData;
    this.companies = ecosystemData.companies || [];
  }

  /**
   * Analyze a company's financial health
   * @param {string} companyId - Company ID (hawksight, kmt, etc.)
   * @returns {Object} Financial analysis with insights and recommendations
   */
  analyze(companyId) {
    const company = this.companies.find(c => c.id === companyId);
    if (!company) return { error: `Company ${companyId} not found` };

    const financials = company.annualFinancials || [];
    const kpis = company.kpis2026F || {};
    const revenueBreakdown = company.revenueBreakdown2026F || [];

    return {
      companyId,
      companyName: company.brandName,
      analysisDate: new Date().toISOString(),
      
      // Core financial metrics
      revenueAnalysis: this._analyzeRevenue(financials, revenueBreakdown, company),
      marginAnalysis: this._analyzeMargins(financials),
      cashAnalysis: this._analyzeCash(financials, company),
      growthAnalysis: this._analyzeGrowth(financials),
      
      // KPI analysis
      kpiAnalysis: this._analyzeKPIs(kpis, company.category),
      
      // Peer comparison
      peerComparison: this._compareWithPeers(company),
      
      // Investment thesis
      investmentThesis: this._evaluateInvestmentThesis(company),
      
      // Key findings
      findings: this._generateFindings(company, financials, kpis),
      
      // Recommendations
      recommendations: this._generateRecommendations(company, financials, kpis)
    };
  }

  /**
   * Generate financial health score (0-100)
   */
  getHealthScore(companyId) {
    const company = this.companies.find(c => c.id === companyId);
    if (!company) return null;

    const financials = company.annualFinancials || [];
    const latest = financials[financials.length - 1] || {};
    
    let score = 50; // Base score
    
    // Revenue growth (up to 20 points)
    const prevYear = financials.length > 1 ? financials[financials.length - 2] : null;
    if (prevYear && prevYear.revenue > 0) {
      const growth = (latest.revenue - prevYear.revenue) / prevYear.revenue;
      if (growth > 0.25) score += 20;
      else if (growth > 0.15) score += 15;
      else if (growth > 0.05) score += 10;
      else if (growth > 0) score += 5;
      else score -= 10;
    }
    
    // Margin health (up to 20 points)
    if (latest.revenue > 0) {
      const margin = (latest.revenue - latest.operatingCosts) / latest.revenue;
      if (margin > 0.25) score += 20;
      else if (margin > 0.15) score += 15;
      else if (margin > 0.05) score += 10;
      else if (margin > 0) score += 5;
      else score -= 10;
    }
    
    // Cash position (up to 15 points)
    if (latest.cashEnding > 0) {
      const monthsRunway = latest.cashEnding / (latest.operatingCosts / 12);
      if (monthsRunway > 12) score += 15;
      else if (monthsRunway > 9) score += 12;
      else if (monthsRunway > 6) score += 8;
      else if (monthsRunway > 3) score += 4;
      else score -= 5;
    }
    
    // Trajectory (up to 15 points)
    if (financials.length >= 3) {
      const last3 = financials.slice(-3);
      const avgGrowth = (last3[2].revenue - last3[0].revenue) / last3[0].revenue;
      if (avgGrowth > 0.5) score += 15;
      else if (avgGrowth > 0.3) score += 12;
      else if (avgGrowth > 0.1) score += 8;
    }
    
    return Math.max(0, Math.min(100, score));
  }

  // ─── PRIVATE ANALYSIS METHODS ──────────────────────────────────

  _analyzeRevenue(financials, revenueBreakdown, company) {
    const latest = financials[financials.length - 1] || {};
    const previous = financials.length > 1 ? financials[financials.length - 2] : null;
    
    const yoyGrowth = previous && previous.revenue > 0 
      ? (latest.revenue - previous.revenue) / previous.revenue 
      : null;
    
    // Revenue concentration
    const topServiceLine = revenueBreakdown.reduce((max, item) => 
      item.share > (max?.share || 0) ? item : max, null
    );
    
    const concentrationRisk = revenueBreakdown.some(item => item.share > 0.6) 
      ? 'high' 
      : revenueBreakdown.some(item => item.share > 0.45) 
        ? 'medium' 
        : 'low';

    return {
      currentRevenue: latest.revenue || 0,
      previousRevenue: previous?.revenue || null,
      yoyGrowth: yoyGrowth,
      yoyGrowthFormatted: yoyGrowth ? `${(yoyGrowth * 100).toFixed(1)}%` : 'N/A',
      revenueBreakdown: revenueBreakdown,
      topServiceLine: topServiceLine,
      concentrationRisk: concentrationRisk,
      totalServiceLines: revenueBreakdown.length,
      revenuePerEmployee: latest.revenue && company?.headcount?.['2026F'] 
        ? Math.round(latest.revenue / company.headcount['2026F']) 
        : null
    };
  }

  _analyzeMargins(financials) {
    const margins = financials
      .filter(f => f.revenue > 0)
      .map(f => ({
        year: f.year,
        grossMargin: (f.revenue - f.operatingCosts) / f.revenue,
        operatingCosts: f.operatingCosts,
        revenue: f.revenue
      }));
    
    const latest = margins[margins.length - 1] || {};
    const previous = margins.length > 1 ? margins[margins.length - 2] : null;
    
    // Margin trend
    let marginTrend = 'stable';
    if (margins.length >= 2) {
      const recent = margins.slice(-2);
      if (recent[1].grossMargin > recent[0].grossMargin + 0.02) marginTrend = 'improving';
      else if (recent[1].grossMargin < recent[0].grossMargin - 0.02) marginTrend = 'declining';
    }
    
    // Operating leverage
    let operatingLeverage = null;
    if (previous && latest.revenue > previous.revenue) {
      const revenueGrowth = (latest.revenue - previous.revenue) / previous.revenue;
      const costGrowth = (latest.operatingCosts - previous.operatingCosts) / previous.operatingCosts;
      operatingLeverage = revenueGrowth > costGrowth ? 'positive' : 'negative';
    }

    return {
      currentMargin: latest.grossMargin || 0,
      currentMarginFormatted: latest.grossMargin ? `${(latest.grossMargin * 100).toFixed(1)}%` : 'N/A',
      previousMargin: previous?.grossMargin || null,
      marginTrend: marginTrend,
      operatingLeverage: operatingLeverage,
      historicalMargins: margins.map(m => ({
        year: m.year,
        margin: m.grossMargin,
        marginFormatted: `${(m.grossMargin * 100).toFixed(1)}%`
      })),
      benchmarkComparison: this._benchmarkMargin(latest.grossMargin)
    };
  }

  _analyzeCash(financials, company) {
    const latest = financials[financials.length - 1] || {};
    const cashEnding = latest.cashEnding || 0;
    const operatingCosts = latest.operatingCosts || 0;
    const monthlyBurn = operatingCosts / 12;
    
    const monthsRunway = monthlyBurn > 0 ? cashEnding / monthlyBurn : null;
    
    // Cash generation
    const ebitda = latest.ebitda || 0;
    const cashGeneration = ebitda > 0 ? 'generating' : 'consuming';
    
    // Cash trajectory
    let cashTrend = 'stable';
    if (financials.length >= 2) {
      const prevCash = financials[financials.length - 2].cashEnding || 0;
      if (cashEnding > prevCash * 1.1) cashTrend = 'growing';
      else if (cashEnding < prevCash * 0.9) cashTrend = 'declining';
    }

    return {
      cashPosition: cashEnding,
      monthlyBurn: Math.round(monthlyBurn),
      monthsRunway: monthsRunway ? monthsRunway.toFixed(1) : null,
      ebitda: ebitda,
      cashGeneration: cashGeneration,
      cashTrend: cashTrend,
      runRate: operatingCosts > 0 ? Math.round(cashEnding * 12 / operatingCosts) : null,
      riskLevel: monthsRunway && monthsRunway < 6 ? 'high' : monthsRunway && monthsRunway < 9 ? 'medium' : 'low'
    };
  }

  _analyzeGrowth(financials) {
    if (financials.length < 2) return { growth: null, trend: 'insufficient_data' };
    
    const yearlyGrowth = [];
    for (let i = 1; i < financials.length; i++) {
      const prev = financials[i - 1];
      const curr = financials[i];
      if (prev.revenue > 0) {
        yearlyGrowth.push({
          year: curr.year,
          growth: (curr.revenue - prev.revenue) / prev.revenue,
          growthFormatted: `${((curr.revenue - prev.revenue) / prev.revenue * 100).toFixed(1)}%`
        });
      }
    }
    
    const avgGrowth = yearlyGrowth.reduce((sum, g) => sum + g.growth, 0) / yearlyGrowth.length;
    const latestGrowth = yearlyGrowth[yearlyGrowth.length - 1]?.growth || 0;
    
    // Growth stage
    let growthStage = 'mature';
    if (avgGrowth > 0.3) growthStage = 'hyper-growth';
    else if (avgGrowth > 0.15) growthStage = 'high-growth';
    else if (avgGrowth > 0.05) growthStage = 'growth';
    else if (avgGrowth > 0) growthStage = 'stable';
    else growthStage = 'declining';

    return {
      averageGrowth: avgGrowth,
      averageGrowthFormatted: `${(avgGrowth * 100).toFixed(1)}%`,
      latestGrowth: latestGrowth,
      latestGrowthFormatted: `${(latestGrowth * 100).toFixed(1)}%`,
      growthStage: growthStage,
      historicalGrowth: yearlyGrowth,
      consistency: this._assessGrowthConsistency(yearlyGrowth)
    };
  }

  _analyzeKPIs(kpis, category) {
    const insights = [];
    
    // Common KPIs
    if (kpis.mrr) {
      insights.push({
        metric: 'MRR',
        value: kpis.mrr,
        formatted: `$${(kpis.mrr / 1000).toFixed(0)}K`,
        insight: kpis.mrr > 50000 ? 'Strong recurring revenue base' : 'Building recurring revenue'
      });
    }
    
    if (kpis.employeeUtilizationRate) {
      const utilization = kpis.employeeUtilizationRate;
      const target = kpis.targetUtilizationRate || 0.76;
      insights.push({
        metric: 'Utilization',
        value: utilization,
        formatted: `${(utilization * 100).toFixed(0)}%`,
        target: target,
        targetFormatted: `${(target * 100).toFixed(0)}%`,
        onTarget: utilization >= target,
        insight: utilization >= target ? 'On or above target' : `${((target - utilization) * 100).toFixed(0)}pp below target`
      });
    }
    
    if (kpis.avgBillRate) {
      insights.push({
        metric: 'Avg Bill Rate',
        value: kpis.avgBillRate,
        formatted: `$${kpis.avgBillRate}/hr`,
        insight: kpis.avgBillRate > 250 ? 'Premium positioning' : 'Competitive rate'
      });
    }
    
    if (kpis.annualLogoChurnRate) {
      const churn = kpis.annualLogoChurnRate;
      insights.push({
        metric: 'Logo Churn',
        value: churn,
        formatted: `${(churn * 100).toFixed(1)}%`,
        insight: churn < 0.05 ? 'Excellent retention' : churn < 0.10 ? 'Good retention' : 'Retention needs attention'
      });
    }
    
    if (kpis.netRevenueRetention) {
      const nrr = kpis.netRevenueRetention;
      insights.push({
        metric: 'Net Revenue Retention',
        value: nrr,
        formatted: `${(nrr * 100).toFixed(0)}%`,
        insight: nrr > 1.2 ? 'Strong expansion' : nrr > 1.0 ? 'Stable with expansion' : 'Revenue contraction risk'
      });
    }
    
    if (kpis.proposalWinRate) {
      const winRate = kpis.proposalWinRate;
      insights.push({
        metric: 'Proposal Win Rate',
        value: winRate,
        formatted: `${(winRate * 100).toFixed(0)}%`,
        insight: winRate > 0.4 ? 'Strong win rate' : winRate > 0.25 ? 'Average win rate' : 'Win rate needs improvement'
      });
    }
    
    return insights;
  }

  _compareWithPeers(company) {
    const peers = this.companies
      .filter(c => c.id !== company.id && c.category !== 'Holding company')
      .map(c => ({
        id: c.id,
        name: c.brandName,
        revenue: c.annualFinancials?.[c.annualFinancials.length - 1]?.revenue || 0,
        headcount: c.headcount?.['2026F'] || 0,
        category: c.category
      }));
    
    const companyRevenue = company.annualFinancials?.[company.annualFinancials.length - 1]?.revenue || 0;
    const companyHeadcount = company.headcount?.['2026F'] || 0;
    
    // Rank by revenue
    const allCompanies = [...peers, { id: company.id, name: company.brandName, revenue: companyRevenue }];
    allCompanies.sort((a, b) => b.revenue - a.revenue);
    const revenueRank = allCompanies.findIndex(c => c.id === company.id) + 1;
    
    // Revenue per employee comparison
    const peerMetrics = peers.map(p => ({
      ...p,
      revenuePerEmployee: p.headcount > 0 ? Math.round(p.revenue / p.headcount) : 0
    }));
    
    const companyRevPerEmp = companyHeadcount > 0 ? Math.round(companyRevenue / companyHeadcount) : 0;
    const avgPeerRevPerEmp = peerMetrics.reduce((sum, p) => sum + p.revenuePerEmployee, 0) / peerMetrics.length;

    return {
      peerCount: peers.length,
      revenueRank: revenueRank,
      totalCompanies: allCompanies.length,
      revenueVsPeers: {
        company: companyRevenue,
        peerAverage: Math.round(peers.reduce((sum, p) => sum + p.revenue, 0) / peers.length),
        peerMax: Math.max(...peers.map(p => p.revenue)),
        peerMin: Math.min(...peers.map(p => p.revenue))
      },
      productivityVsPeers: {
        company: companyRevPerEmp,
        peerAverage: Math.round(avgPeerRevPerEmp),
        aboveAverage: companyRevPerEmp > avgPeerRevPerEmp
      }
    };
  }

  _evaluateInvestmentThesis(company) {
    const financials = company.annualFinancials || [];
    const latest = financials[financials.length - 1] || {};
    const kpis = company.kpis2026F || {};
    
    const thesis = {
      strengths: [],
      risks: [],
      opportunities: [],
      overallRating: 'neutral'
    };
    
    // Revenue growth strength
    if (financials.length >= 2) {
      const prev = financials[financials.length - 2];
      const growth = (latest.revenue - prev.revenue) / prev.revenue;
      if (growth > 0.2) thesis.strengths.push('Strong revenue growth trajectory');
      else if (growth > 0.1) thesis.strengths.push('Solid revenue growth');
      else if (growth < 0) thesis.risks.push('Revenue declining');
    }
    
    // Margin strength
    if (latest.revenue > 0) {
      const margin = (latest.revenue - latest.operatingCosts) / latest.revenue;
      if (margin > 0.2) thesis.strengths.push('Strong margins');
      else if (margin > 0.1) thesis.strengths.push('Healthy margins');
      else if (margin < 0) thesis.risks.push('Operating at a loss');
    }
    
    // Cash position
    if (latest.cashEnding > 0) {
      const monthsRunway = latest.cashEnding / (latest.operatingCosts / 12);
      if (monthsRunway > 9) thesis.strengths.push('Strong cash position');
      else if (monthsRunway < 6) thesis.risks.push('Limited cash runway');
    }
    
    // Recurring revenue
    if (kpis.mrr || kpis.netRevenueRetention) {
      if (kpis.netRevenueRetention > 1.1) thesis.strengths.push('Strong net revenue retention');
      if (kpis.annualLogoChurnRate && kpis.annualLogoChurnRate > 0.1) thesis.risks.push('High customer churn');
    }
    
    // Overall rating
    if (thesis.strengths.length > thesis.risks.length + 1) thesis.overallRating = 'strong';
    else if (thesis.strengths.length > thesis.risks.length) thesis.overallRating = 'positive';
    else if (thesis.risks.length > thesis.strengths.length) thesis.overallRating = 'watch';
    else thesis.overallRating = 'neutral';
    
    return thesis;
  }

  _generateFindings(company, financials, kpis) {
    const findings = [];
    const latest = financials[financials.length - 1] || {};
    
    // Revenue finding
    if (latest.revenue > 0) {
      findings.push({
        type: 'revenue',
        severity: 'info',
        finding: `${company.brandName} projects $${(latest.revenue / 1000000).toFixed(1)}M revenue in 2026F`,
        impact: 'medium'
      });
    }
    
    // Margin finding
    if (latest.revenue > 0) {
      const margin = (latest.revenue - latest.operatingCosts) / latest.revenue;
      if (margin < 0.1) {
        findings.push({
          type: 'margin',
          severity: 'warning',
          finding: `Operating margin of ${(margin * 100).toFixed(1)}% is below 10% threshold`,
          impact: 'high'
        });
      }
    }
    
    // Utilization finding (for consulting firms)
    if (kpis.employeeUtilizationRate) {
      const target = kpis.targetUtilizationRate || 0.76;
      if (kpis.employeeUtilizationRate < target) {
        findings.push({
          type: 'utilization',
          severity: 'warning',
          finding: `Utilization at ${(kpis.employeeUtilizationRate * 100).toFixed(0)}% vs ${(target * 100).toFixed(0)}% target`,
          impact: 'medium'
        });
      }
    }
    
    // Cash finding
    if (latest.cashEnding > 0 && latest.operatingCosts > 0) {
      const monthsRunway = latest.cashEnding / (latest.operatingCosts / 12);
      if (monthsRunway < 6) {
        findings.push({
          type: 'cash',
          severity: 'critical',
          finding: `Only ${monthsRunway.toFixed(1)} months of cash runway remaining`,
          impact: 'critical'
        });
      }
    }
    
    return findings;
  }

  _generateRecommendations(company, financials, kpis) {
    const recommendations = [];
    const latest = financials[financials.length - 1] || {};
    
    // Margin improvement
    if (latest.revenue > 0) {
      const margin = (latest.revenue - latest.operatingCosts) / latest.revenue;
      if (margin < 0.15) {
        recommendations.push({
          area: 'operations',
          priority: 'high',
          recommendation: 'Implement cost optimization program to improve margins',
          expectedImpact: '5-10 margin improvement within 12 months',
          effort: 'high',
          timeframe: '6-12 months'
        });
      }
    }
    
    // Utilization improvement (for consulting firms)
    if (kpis.employeeUtilizationRate && kpis.targetUtilizationRate) {
      if (kpis.employeeUtilizationRate < kpis.targetUtilizationRate) {
        const gap = kpis.targetUtilizationRate - kpis.employeeUtilizationRate;
        recommendations.push({
          area: 'productivity',
          priority: 'medium',
          recommendation: `Close ${(gap * 100).toFixed(0)}pp utilization gap through pipeline management`,
          expectedImpact: `Additional $${Math.round(gap * company.headcount?.['2026F'] * kpis.avgBillRate * 160 / 1000)}K annual revenue potential`,
          effort: 'medium',
          timeframe: '3-6 months'
        });
      }
    }
    
    // Cash management
    if (latest.cashEnding > 0 && latest.operatingCosts > 0) {
      const monthsRunway = latest.cashEnding / (latest.operatingCosts / 12);
      if (monthsRunway < 9) {
        recommendations.push({
          area: 'finance',
          priority: monthsRunway < 6 ? 'critical' : 'high',
          recommendation: 'Establish or increase cash reserves to 9+ months runway',
          expectedImpact: 'Reduced financial risk and improved strategic flexibility',
          effort: 'medium',
          timeframe: '3-6 months'
        });
      }
    }
    
    // Revenue diversification
    const revenueBreakdown = company.revenueBreakdown2026F || [];
    if (revenueBreakdown.length > 0) {
      const topService = revenueBreakdown.reduce((max, item) => item.share > (max?.share || 0) ? item : max, null);
      if (topService && topService.share > 0.6) {
        recommendations.push({
          area: 'strategy',
          priority: 'medium',
          recommendation: 'Diversify revenue streams to reduce concentration risk',
          expectedImpact: 'Reduced vulnerability to single service line disruption',
          effort: 'high',
          timeframe: '12-24 months'
        });
      }
    }
    
    return recommendations;
  }

  _benchmarkMargin(margin) {
    if (margin > 0.3) return { rating: 'excellent', benchmark: 'Top quartile for professional services' };
    if (margin > 0.2) return { rating: 'strong', benchmark: 'Above average for professional services' };
    if (margin > 0.1) return { rating: 'average', benchmark: 'In line with professional services' };
    if (margin > 0) return { rating: 'below_average', benchmark: 'Below average - improvement needed' };
    return { rating: 'poor', benchmark: 'Operating at a loss' };
  }

  _assessGrowthConsistency(growthData) {
    if (growthData.length < 2) return 'insufficient_data';
    const growthRates = growthData.map(g => g.growth);
    const avg = growthRates.reduce((s, g) => s + g, 0) / growthRates.length;
    const variance = growthRates.reduce((s, g) => s + Math.pow(g - avg, 2), 0) / growthRates.length;
    const stdDev = Math.sqrt(variance);
    
    if (stdDev < 0.05) return 'very_consistent';
    if (stdDev < 0.1) return 'consistent';
    if (stdDev < 0.2) return 'moderate';
    return 'volatile';
  }
}

module.exports = FinancialAnalysis;
