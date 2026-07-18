/**
 * KMT Consulting Group - Performance Dashboard
 * KMT's own operational metrics and performance tracking
 * 
 * Tracks:
 * - Financial performance (revenue, margin, growth)
 * - Utilization and productivity metrics
 * - Client satisfaction and engagement health
 * - Team performance and development
 * - Operational efficiency
 */

class PerformanceDashboard {
  constructor() {
    this.metrics = new Map();
    this.targets = new Map();
    this.history = new Map();
    this._initialized = false;
  }

  initialize() {
    if (this._initialized) return this;
    this._loadMetrics();
    this._loadTargets();
    this._initialized = true;
    return this;
  }

  // ─── FINANCIAL METRICS ──────────────────────────────────────────

  getFinancialSummary(period = 'ytd') {
    const metrics = this.metrics.get('financial') || {};
    return {
      revenue: metrics.revenue?.[period] || 0,
      target: metrics.revenueTarget?.[period] || 0,
      attainment: this._calculateAttainment(
        metrics.revenue?.[period], 
        metrics.revenueTarget?.[period]
      ),
      grossMargin: metrics.grossMargin?.[period] || 0,
      operatingMargin: metrics.operatingMargin?.[period] || 0,
      revenueGrowth: metrics.revenueGrowth?.[period] || 0,
      averageBillRate: metrics.averageBillRate || 0
    };
  }

  getRevenueByServiceLine() {
    const breakdown = this.metrics.get('revenueByServiceLine') || {};
    return Object.entries(breakdown).map(([name, data]) => ({
      name,
      revenue: data.revenue || 0,
      target: data.target || 0,
      percentage: data.percentage || 0,
      attainment: this._calculateAttainment(data.revenue, data.target)
    }));
  }

  getRevenueByClient() {
    const breakdown = this.metrics.get('revenueByClient') || {};
    return Object.entries(breakdown).map(([name, data]) => ({
      name,
      revenue: data.revenue || 0,
      target: data.target || 0,
      engagements: data.engagements || 0,
      averageEngagementSize: data.engagements > 0 ? data.revenue / data.engagements : 0
    }));
  }

  // ─── UTILIZATION METRICS ────────────────────────────────────────

  getUtilizationMetrics() {
    const metrics = this.metrics.get('utilization') || {};
    return {
      overall: metrics.overall || 0,
      target: metrics.target || 0,
      byRole: metrics.byRole || [],
      byEngagement: metrics.byEngagement || [],
      billableHours: metrics.billableHours || 0,
      nonBillableHours: metrics.nonBillableHours || 0,
      targetHours: metrics.targetHours || 0
    };
  }

  getTeamProductivity() {
    const productivity = this.metrics.get('teamProductivity') || {};
    return Object.entries(productivity).map(([name, data]) => ({
      name,
      role: data.role,
      utilization: data.utilization || 0,
      billableHours: data.billableHours || 0,
      revenue: data.revenue || 0,
      engagements: data.engagements || 0,
      csat: data.csat || null
    }));
  }

  // ─── ENGAGEMENT HEALTH ──────────────────────────────────────────

  getEngagementHealthSummary() {
    const health = this.metrics.get('engagementHealth') || {};
    return {
      total: health.total || 0,
      byStatus: {
        green: health.green || 0,
        yellow: health.yellow || 0,
        red: health.red || 0
      },
      averageCSAT: health.averageCSAT || 0,
      onTimeDelivery: health.onTimeDelivery || 0,
      onBudgetDelivery: health.onBudgetDelivery || 0,
      pipeline: {
        intake: health.pipeline?.intake || 0,
        scoping: health.pipeline?.scoping || 0,
        proposal: health.pipeline?.proposal || 0,
        active: health.pipeline?.active || 0,
        delivery: health.pipeline?.delivery || 0,
        closed: health.pipeline?.closed || 0
      }
    };
  }

  getClientSatisfaction() {
    const csat = this.metrics.get('clientSatisfaction') || {};
    return {
      overall: csat.overall || 0,
      byClient: csat.byClient || [],
      responseRate: csat.responseRate || 0,
      nps: csat.nps || 0,
      lastSurveyDate: csat.lastSurveyDate || null
    };
  }

  // ─── OPERATIONAL METRICS ────────────────────────────────────────

  getOperationalMetrics() {
    const ops = this.metrics.get('operational') || {};
    return {
      averageEngagementDuration: ops.averageEngagementDuration || 0,
      averageEngagementSize: ops.averageEngagementSize || 0,
      repeatClientRate: ops.repeatClientRate || 0,
      newClientAcquisition: ops.newClientAcquisition || 0,
      proposalWinRate: ops.proposalWinRate || 0,
      averageTimeToStart: ops.averageTimeToStart || 0,
      deliverableQualityScore: ops.deliverableQualityScore || 0
    };
  }

  // ─── TREND ANALYSIS ─────────────────────────────────────────────

  getTrend(metricName, periods = 6) {
    const history = this.history.get(metricName) || [];
    return history.slice(-periods);
  }

  getYoYComparison() {
    return {
      revenue: {
        current: this.metrics.get('financial')?.revenue?.ytd || 0,
        previous: this.history.get('revenue')?.[0] || 0,
        growth: this._calculateGrowth(
          this.history.get('revenue')?.[0] || 0,
          this.metrics.get('financial')?.revenue?.ytd || 0
        )
      },
      utilization: {
        current: this.metrics.get('utilization')?.overall || 0,
        previous: this.history.get('utilization')?.[0] || 0,
        change: (this.metrics.get('utilization')?.overall || 0) - 
                (this.history.get('utilization')?.[0] || 0)
      }
    };
  }

  // ─── EXECUTIVE SUMMARY ──────────────────────────────────────────

  getExecutiveSummary() {
    return {
      financial: this.getFinancialSummary(),
      utilization: this.getUtilizationMetrics(),
      engagementHealth: this.getEngagementHealthSummary(),
      clientSatisfaction: this.getClientSatisfaction(),
      operational: this.getOperationalMetrics(),
      yoyComparison: this.getYoYComparison(),
      generatedAt: new Date().toISOString()
    };
  }

  // ─── PRIVATE HELPERS ─────────────────────────────────────────────

  _loadMetrics() {
    this.metrics.clear();
  }

  _loadTargets() {
    this.targets.clear();
  }

  _calculateAttainment(actual, target) {
    if (!target || target === 0) return 0;
    return (actual / target) * 100;
  }

  _calculateGrowth(previous, current) {
    if (!previous || previous === 0) return 0;
    return ((current - previous) / previous) * 100;
  }

  _generateId() {
    return 'DASH-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PerformanceDashboard;
}
