/**
 * KMT Consulting Group - Operational Analysis Engine
 * 
 * Analyzes operational efficiency, process maturity, and improvement opportunities:
 * - Service line performance
 * - Client concentration and retention
 * - Delivery efficiency
 * - Process maturity assessment
 * - Operational risk identification
 */

class OperationalAnalysis {
  constructor(ecosystemData) {
    this.data = ecosystemData;
    this.companies = ecosystemData.companies || [];
    this.clients = ecosystemData.clientDatabase || [];
    this.projects = ecosystemData.majorProjectsPipeline || [];
    this.intercompany = ecosystemData.intercompanyTransactions2026F || [];
  }

  /**
   * Analyze a company's operational health
   * @param {string} companyId - Company ID
   * @returns {Object} Operational analysis with insights and recommendations
   */
  analyze(companyId) {
    const company = this.companies.find(c => c.id === companyId);
    if (!company) return { error: `Company ${companyId} not found` };

    const companyClients = this.clients.filter(c => c.companyId === companyId);
    const companyProjects = this.projects.filter(p => p.companyId === companyId);
    const companyIntercompany = this.intercompany.filter(
      t => t.fromCompanyId === companyId || t.toCompanyId === companyId
    );

    return {
      companyId,
      companyName: company.brandName,
      analysisDate: new Date().toISOString(),
      
      // Service line analysis
      serviceLineAnalysis: this._analyzeServiceLines(company, companyProjects),
      
      // Client analysis
      clientAnalysis: this._analyzeClients(companyClients, company),
      
      // Delivery analysis
      deliveryAnalysis: this._analyzeDelivery(companyProjects),
      
      // Intercompany analysis
      intercompanyAnalysis: this._analyzeIntercompany(companyIntercompany, companyId),
      
      // Operational maturity
      maturityAssessment: this._assessMaturity(company, companyClients, companyProjects),
      
      // Process efficiency
      processEfficiency: this._analyzeProcessEfficiency(company, companyClients),
      
      // Findings
      findings: this._generateFindings(company, companyClients, companyProjects),
      
      // Recommendations
      recommendations: this._generateRecommendations(company, companyClients, companyProjects)
    };
  }

  /**
   * Get operational health score (0-100)
   */
  getHealthScore(companyId) {
    const company = this.companies.find(c => c.id === companyId);
    if (!company) return null;

    const companyClients = this.clients.filter(c => c.companyId === companyId);
    const companyProjects = this.projects.filter(p => p.companyId === companyId);
    
    let score = 50; // Base
    
    // Client diversification (up to 20 points)
    if (companyClients.length >= 3) score += 20;
    else if (companyClients.length >= 2) score += 15;
    else if (companyClients.length >= 1) score += 10;
    else score += 5;
    
    // Client retention (up to 15 points)
    const activeClients = companyClients.filter(c => c.status === 'active').length;
    const renewalDue = companyClients.filter(c => c.status === 'renewal_due').length;
    if (activeClients > 0 && renewalDue === 0) score += 15;
    else if (activeClients > 0) score += 10;
    
    // Project health (up to 15 points)
    const deliveredProjects = companyProjects.filter(p => p.stage === 'complete').length;
    const activeProjects = companyProjects.filter(p => p.stage === 'in_delivery').length;
    if (deliveredProjects > 0) score += 15;
    else if (activeProjects > 0) score += 10;
    
    return Math.max(0, Math.min(100, score));
  }

  // ─── PRIVATE ANALYSIS METHODS ──────────────────────────────────

  _analyzeServiceLines(company, projects) {
    const revenueBreakdown = company.revenueBreakdown2026F || [];
    const serviceOfferings = company.serviceOfferings || [];
    
    return serviceOfferings.map(offering => {
      const revenue = revenueBreakdown.find(r => r.serviceLineId === offering.id);
      const serviceProjects = projects.filter(p => 
        p.clientId && this.clients.some(c => c.clientId === p.clientId && c.serviceLineId === offering.id)
      );
      
      return {
        id: offering.id,
        name: offering.name,
        revenueModel: offering.revenueModel,
        revenue: revenue?.amount || 0,
        revenueShare: revenue?.share || 0,
        activeProjects: serviceProjects.length,
        projectHealth: serviceProjects.map(p => ({
          name: p.name,
          stage: p.stage,
          expectedRevenue: p.expectedRevenue,
          margin: p.grossMarginTarget
        }))
      };
    });
  }

  _analyzeClients(clients, company) {
    if (clients.length === 0) {
      return {
        totalClients: 0,
        activeClients: 0,
        concentration: 'no_clients',
        insights: ['No external clients in database - internal consulting model']
      };
    }
    
    const activeClients = clients.filter(c => c.status === 'active');
    const renewalDue = clients.filter(c => c.status === 'renewal_due');
    const pipelineClients = clients.filter(c => c.status === 'pipeline');
    
    // Concentration analysis
    const totalACV = clients.reduce((sum, c) => sum + (c.annualContractValue || 0), 0);
    const topClient = clients.reduce((max, c) => 
      (c.annualContractValue || 0) > (max?.annualContractValue || 0) ? c : max, null
    );
    const topClientShare = topClient ? topClient.annualContractValue / totalACV : 0;
    
    // Industry diversification
    const industries = [...new Set(clients.map(c => c.industry))];
    
    // Geographic diversification
    const countries = [...new Set(clients.map(c => c.country))];
    
    // Retention metrics
    const renewalRate = clients.filter(c => 
      c.status === 'active' && c.renewalDate && new Date(c.renewalDate) > new Date()
    ).length / Math.max(1, activeClients.length);

    return {
      totalClients: clients.length,
      activeClients: activeClients.length,
      renewalDue: renewalDue.length,
      pipelineClients: pipelineClients.length,
      totalACV: totalACV,
      averageACV: Math.round(totalACV / clients.length),
      topClient: topClient,
      topClientShare: topClientShare,
      concentrationRisk: topClientShare > 0.4 ? 'high' : topClientShare > 0.25 ? 'medium' : 'low',
      industryDiversification: industries,
      industryCount: industries.length,
      geographicDiversification: countries,
      countryCount: countries.length,
      renewalRate: renewalRate,
      insights: this._generateClientInsights(clients, company)
    };
  }

  _generateClientInsights(clients, company) {
    const insights = [];
    
    if (clients.length === 0) {
      insights.push('No external clients - operating as internal consulting unit');
      return insights;
    }
    
    const activeClients = clients.filter(c => c.status === 'active');
    const renewalDue = clients.filter(c => c.status === 'renewal_due');
    
    if (renewalDue.length > 0) {
      insights.push(`${renewalDue.length} client(s) with renewal due - prioritize retention`);
    }
    
    const totalACV = clients.reduce((sum, c) => sum + (c.annualContractValue || 0), 0);
    if (totalACV > 0) {
      const topClient = clients.reduce((max, c) => 
        (c.annualContractValue || 0) > (max?.annualContractValue || 0) ? c : max, null
      );
      if (topClient && topClient.annualContractValue / totalACV > 0.4) {
        insights.push(`High concentration: ${topClient.clientName} represents ${(topClient.annualContractValue / totalACV * 100).toFixed(0)}% of ACV`);
      }
    }
    
    const industries = [...new Set(clients.map(c => c.industry))];
    if (industries.length < 3) {
      insights.push('Limited industry diversification - consider expanding sector coverage');
    }
    
    return insights;
  }

  _analyzeDelivery(projects) {
    if (projects.length === 0) {
      return {
        totalProjects: 0,
        pipelineValue: 0,
        deliveryHealth: 'no_data'
      };
    }
    
    const stages = {
      contracted: projects.filter(p => p.stage === 'contracted'),
      in_delivery: projects.filter(p => p.stage === 'in_delivery'),
      complete: projects.filter(p => p.stage === 'complete'),
      at_risk: projects.filter(p => p.stage === 'at_risk')
    };
    
    const totalExpectedRevenue = projects.reduce((sum, p) => sum + (p.expectedRevenue || 0), 0);
    const weightedPipeline = projects.reduce((sum, p) => 
      sum + ((p.expectedRevenue || 0) * (p.probability || 0)), 0
    );
    
    // Margin analysis
    const avgMargin = projects.reduce((sum, p) => sum + (p.grossMarginTarget || 0), 0) / projects.length;
    
    // Timeline analysis
    const now = new Date();
    const overdueProjects = projects.filter(p => 
      p.expectedCloseDate && new Date(p.expectedCloseDate) < now && p.stage !== 'complete'
    );
    
    return {
      totalProjects: projects.length,
      stages: {
        contracted: stages.contracted.length,
        in_delivery: stages.in_delivery.length,
        complete: stages.complete.length,
        at_risk: stages.at_risk.length
      },
      totalExpectedRevenue: totalExpectedRevenue,
      weightedPipeline: weightedPipeline,
      averageMargin: avgMargin,
      averageMarginFormatted: `${(avgMargin * 100).toFixed(1)}%`,
      overdueProjects: overdueProjects.length,
      deliveryHealth: stages.at_risk.length > 0 ? 'at_risk' : 
                      overdueProjects.length > 0 ? 'attention_needed' : 'healthy'
    };
  }

  _analyzeIntercompany(transactions, companyId) {
    const incoming = transactions.filter(t => t.toCompanyId === companyId);
    const outgoing = transactions.filter(t => t.fromCompanyId === companyId);
    
    const incomingTotal = incoming.reduce((sum, t) => sum + (t.amount || 0), 0);
    const outgoingTotal = outgoing.reduce((sum, t) => sum + (t.amount || 0), 0);
    
    return {
      incoming: {
        count: incoming.length,
        total: incomingTotal,
        transactions: incoming.map(t => ({
          from: t.fromCompanyId,
          description: t.description,
          amount: t.amount,
          type: t.type
        }))
      },
      outgoing: {
        count: outgoing.length,
        total: outgoingTotal,
        transactions: outgoing.map(t => ({
          to: t.toCompanyId,
          description: t.description,
          amount: t.amount,
          type: t.type
        }))
      },
      netPosition: incomingTotal - outgoingTotal,
      netPositionFormatted: `$${((incomingTotal - outgoingTotal) / 1000).toFixed(0)}K`
    };
  }

  _assessMaturity(company, clients, projects) {
    const factors = [];
    let score = 0;
    
    // Client management maturity
    if (clients.length > 0) {
      const activeClients = clients.filter(c => c.status === 'active');
      if (activeClients.length > 0) {
        score += 25;
        factors.push({ factor: 'Client Management', score: 25, maxScore: 25, status: 'established' });
      } else {
        score += 10;
        factors.push({ factor: 'Client Management', score: 10, maxScore: 25, status: 'developing' });
      }
    } else {
      factors.push({ factor: 'Client Management', score: 0, maxScore: 25, status: 'not_applicable' });
    }
    
    // Delivery maturity
    if (projects.length > 0) {
      const delivered = projects.filter(p => p.stage === 'complete');
      if (delivered.length > 0) {
        score += 25;
        factors.push({ factor: 'Delivery Execution', score: 25, maxScore: 25, status: 'established' });
      } else {
        score += 15;
        factors.push({ factor: 'Delivery Execution', score: 15, maxScore: 25, status: 'developing' });
      }
    } else {
      factors.push({ factor: 'Delivery Execution', score: 0, maxScore: 25, status: 'nascent' });
    }
    
    // Service line maturity
    const serviceLines = company.serviceOfferings || [];
    if (serviceLines.length >= 3) {
      score += 25;
      factors.push({ factor: 'Service Line Portfolio', score: 25, maxScore: 25, status: 'established' });
    } else if (serviceLines.length >= 2) {
      score += 15;
      factors.push({ factor: 'Service Line Portfolio', score: 15, maxScore: 25, status: 'developing' });
    } else {
      score += 5;
      factors.push({ factor: 'Service Line Portfolio', score: 5, maxScore: 25, status: 'nascent' });
    }
    
    // Financial maturity
    const financials = company.annualFinancials || [];
    const latest = financials[financials.length - 1];
    if (latest && latest.revenue > 0 && latest.ebitda !== undefined) {
      score += 25;
      factors.push({ factor: 'Financial Management', score: 25, maxScore: 25, status: 'established' });
    } else {
      factors.push({ factor: 'Financial Management', score: 0, maxScore: 25, status: 'nascent' });
    }
    
    // Overall maturity level
    let maturityLevel = 'nascent';
    if (score >= 75) maturityLevel = 'established';
    else if (score >= 50) maturityLevel = 'developing';
    else if (score >= 25) maturityLevel = 'emerging';
    
    return {
      overallScore: score,
      maxScore: 100,
      maturityLevel: maturityLevel,
      factors: factors
    };
  }

  _analyzeProcessEfficiency(company, clients) {
    const kpis = company.kpis2026F || {};
    const insights = [];
    
    // Utilization efficiency
    if (kpis.employeeUtilizationRate) {
      const target = kpis.targetUtilizationRate || 0.76;
      const gap = target - kpis.employeeUtilizationRate;
      if (gap > 0.05) {
        insights.push({
          process: 'Resource Utilization',
          efficiency: 'below_target',
          gap: gap,
          insight: `Utilization ${(gap * 100).toFixed(0)}pp below target - capacity available`
        });
      }
    }
    
    // Proposal win rate
    if (kpis.proposalWinRate !== undefined) {
      const winRate = kpis.proposalWinRate;
      if (winRate < 0.25) {
        insights.push({
          process: 'Business Development',
          efficiency: 'needs_improvement',
          winRate: winRate,
          insight: `Win rate ${(winRate * 100).toFixed(0)}% is below 25% threshold`
        });
      } else if (winRate > 0.4) {
        insights.push({
          process: 'Business Development',
          efficiency: 'strong',
          winRate: winRate,
          insight: `Win rate ${(winRate * 100).toFixed(0)}% indicates strong positioning`
        });
      }
    }
    
    // Client acquisition cost
    if (kpis.avgClientCac && kpis.avgClientLtv) {
      const ltvCacRatio = kpis.avgClientLtv / kpis.avgClientCac;
      if (ltvCacRatio < 3) {
        insights.push({
          process: 'Client Economics',
          efficiency: 'concerning',
          ltvCacRatio: ltvCacRatio,
          insight: `LTV/CAC ratio ${ltvCacRatio.toFixed(1)}x is below 3x target`
        });
      } else if (ltvCacRatio > 5) {
        insights.push({
          process: 'Client Economics',
          efficiency: 'strong',
          ltvCacRatio: ltvCacRatio,
          insight: `LTV/CAC ratio ${ltvCacRatio.toFixed(1)}x indicates efficient acquisition`
        });
      }
    }
    
    // Delivery margin
    if (kpis.deliveryGrossMargin) {
      const margin = kpis.deliveryGrossMargin;
      if (margin < 0.3) {
        insights.push({
          process: 'Delivery Efficiency',
          efficiency: 'below_target',
          margin: margin,
          insight: `Delivery margin ${(margin * 100).toFixed(0)}% is below 30% target`
        });
      }
    }
    
    return insights;
  }

  _generateFindings(company, clients, projects) {
    const findings = [];
    
    // Client findings
    if (clients.length > 0) {
      const activeClients = clients.filter(c => c.status === 'active');
      const renewalDue = clients.filter(c => c.status === 'renewal_due');
      
      if (renewalDue.length > 0) {
        findings.push({
          type: 'client_retention',
          severity: 'warning',
          finding: `${renewalDue.length} client(s) with renewal due soon`,
          impact: 'high'
        });
      }
      
      const totalACV = clients.reduce((sum, c) => sum + (c.annualContractValue || 0), 0);
      const topClient = clients.reduce((max, c) => 
        (c.annualContractValue || 0) > (max?.annualContractValue || 0) ? c : max, null
      );
      
      if (topClient && topClient.annualContractValue / totalACV > 0.4) {
        findings.push({
          type: 'client_concentration',
          severity: 'warning',
          finding: `High client concentration: ${topClient.clientName} is ${((topClient.annualContractValue / totalACV) * 100).toFixed(0)}% of ACV`,
          impact: 'medium'
        });
      }
    }
    
    // Project findings
    const atRiskProjects = projects.filter(p => p.stage === 'at_risk');
    if (atRiskProjects.length > 0) {
      findings.push({
        type: 'project_risk',
        severity: 'critical',
        finding: `${atRiskProjects.length} project(s) at risk`,
        impact: 'high'
      });
    }
    
    const overdueProjects = projects.filter(p => 
      p.expectedCloseDate && new Date(p.expectedCloseDate) < new Date() && p.stage !== 'complete'
    );
    if (overdueProjects.length > 0) {
      findings.push({
        type: 'delivery_delay',
        severity: 'warning',
        finding: `${overdueProjects.length} project(s) past expected close date`,
        impact: 'medium'
      });
    }
    
    // KPI findings
    const kpis = company.kpis2026F || {};
    if (kpis.proposalWinRate !== undefined && kpis.proposalWinRate < 0.25) {
      findings.push({
        type: 'business_development',
        severity: 'warning',
        finding: `Proposal win rate ${(kpis.proposalWinRate * 100).toFixed(0)}% is below 25%`,
        impact: 'medium'
      });
    }
    
    if (kpis.avgClientCac && kpis.avgClientLtv) {
      const ltvCacRatio = kpis.avgClientLtv / kpis.avgClientCac;
      if (ltvCacRatio < 3) {
        findings.push({
          type: 'client_economics',
          severity: 'warning',
          finding: `LTV/CAC ratio ${ltvCacRatio.toFixed(1)}x is below 3x target`,
          impact: 'medium'
        });
      }
    }
    
    return findings;
  }

  _generateRecommendations(company, clients, projects) {
    const recommendations = [];
    const kpis = company.kpis2026F || {};
    
    // Client retention
    const renewalDue = clients.filter(c => c.status === 'renewal_due');
    if (renewalDue.length > 0) {
      recommendations.push({
        area: 'client_retention',
        priority: 'high',
        recommendation: `Prioritize renewal conversations for ${renewalDue.length} client(s) with renewals due`,
        expectedImpact: 'Protect existing revenue and relationship',
        effort: 'medium',
        timeframe: '1-2 months'
      });
    }
    
    // Client diversification
    const totalACV = clients.reduce((sum, c) => sum + (c.annualContractValue || 0), 0);
    const topClient = clients.reduce((max, c) => 
      (c.annualContractValue || 0) > (max?.annualContractValue || 0) ? c : max, null
    );
    if (topClient && topClient.annualContractValue / totalACV > 0.4) {
      recommendations.push({
        area: 'client_diversification',
        priority: 'medium',
        recommendation: `Reduce concentration risk - ${topClient.clientName} represents ${(topClient.annualContractValue / totalACV * 100).toFixed(0)}% of ACV`,
        expectedImpact: 'Reduced vulnerability to single client loss',
        effort: 'high',
        timeframe: '6-12 months'
      });
    }
    
    // Win rate improvement
    if (kpis.proposalWinRate !== undefined && kpis.proposalWinRate < 0.25) {
      recommendations.push({
        area: 'business_development',
        priority: 'high',
        recommendation: 'Review proposal process and win/loss patterns to improve conversion',
        expectedImpact: `Improving win rate from ${(kpis.proposalWinRate * 100).toFixed(0)}% to 30%+ increases revenue`,
        effort: 'medium',
        timeframe: '3-6 months'
      });
    }
    
    // Client economics
    if (kpis.avgClientCac && kpis.avgClientLtv) {
      const ltvCacRatio = kpis.avgClientLtv / kpis.avgClientCac;
      if (ltvCacRatio < 3) {
        recommendations.push({
          area: 'client_economics',
          priority: 'medium',
          recommendation: 'Improve client economics through higher ACV, lower CAC, or better retention',
          expectedImpact: `LTV/CAC ratio needs to reach 3x+ for sustainable growth`,
          effort: 'high',
          timeframe: '6-12 months'
        });
      }
    }
    
    // At-risk projects
    const atRiskProjects = projects.filter(p => p.stage === 'at_risk');
    if (atRiskProjects.length > 0) {
      recommendations.push({
        area: 'delivery',
        priority: 'critical',
        recommendation: `Triage ${atRiskProjects.length} at-risk project(s) to prevent revenue loss`,
        expectedImpact: 'Protect contracted revenue and client relationships',
        effort: 'high',
        timeframe: 'immediate'
      });
    }
    
    return recommendations;
  }
}

module.exports = OperationalAnalysis;
