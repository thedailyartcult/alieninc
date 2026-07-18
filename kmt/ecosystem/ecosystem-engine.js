/**
 * Alien.Inc Living Ecosystem Engine
 * 
 * A self-evolving organism where 7 companies breathe together.
 * Each day, companies:
 * - Generate revenue based on clients and contracts
 * - Accumulate costs (fixed + variable)
 * - Experience events (wins, losses, risks)
 * - Interact with each other (intercompany flows)
 * - Respond to market dynamics
 * 
 * The ecosystem is alive. It grows, contracts, and adapts.
 */

const fs = require('fs');
const path = require('path');

class EcosystemEngine {
  constructor() {
    this.companies = new Map();
    this.events = [];
    this.history = [];
    this.marketConditions = {};
    this.day = 0;
    this.startDate = null;
    this._initialized = false;
  }

  /**
   * Initialize the ecosystem with base data
   */
  initialize(dataPath) {
    if (this._initialized) return this;

    const fullPath = dataPath || path.join(__dirname, '../../data/alieninc-ecosystem.json');
    const data = JSON.parse(fs.readFileSync(fullPath, 'utf8'));

    // Load companies into memory
    for (const company of data.companies) {
      this.companies.set(company.id, {
        ...company,
        // Runtime state
        cash: company.annualFinancials?.[company.annualFinancials.length - 1]?.cashEnding || 0,
        dailyRevenue: 0,
        dailyCosts: 0,
        dailyEbitda: 0,
        clients: [],
        projects: [],
        health: 100,
        momentum: 0, // -10 to +10
        alerts: [],
        lastEvent: null
      });
    }

    // Load client data
    if (data.clientDatabase) {
      for (const client of data.clientDatabase) {
        const company = this.companies.get(client.companyId);
        if (company) {
          company.clients.push(client);
        }
      }
    }

    // Load project data
    if (data.majorProjectsPipeline) {
      for (const project of data.majorProjectsPipeline) {
        const company = this.companies.get(project.companyId);
        if (company) {
          company.projects.push(project);
        }
      }
    }

    // Load intercompany transactions
    this.intercompanyTransactions = data.intercompanyTransactions2026F || [];

    // Initialize market conditions
    this.marketConditions = {
      growthRate: 1.02, // 2% monthly growth
      riskLevel: 1.0, // 1.0 = normal
      competitionIntensity: 1.0,
      cashAvailability: 1.0
    };

    this.startDate = new Date();
    this._initialized = true;
    return this;
  }

  /**
   * Advance the ecosystem by one day
   */
  simulateDay() {
    if (!this._initialized) return { error: 'Not initialized' };

    this.day++;
    const currentDate = new Date(this.startDate);
    currentDate.setDate(currentDate.getDate() + this.day);

    const dailyEvents = [];

    // 1. Each company operates
    for (const [id, company] of this.companies) {
      const dayResult = this._simulateCompanyDay(company, currentDate);
      dailyEvents.push(...dayResult.events);
    }

    // 2. Intercompany flows execute
    const flowEvents = this._executeIntercompanyFlows(currentDate);
    dailyEvents.push(...flowEvents);

    // 3. Market dynamics shift
    this._updateMarketConditions(currentDate);

    // 4. Cross-company effects
    this._applyCrossCompanyEffects();

    // 5. Record history
    this._recordHistory(currentDate);

    // 6. Generate alerts
    const alerts = this._checkAlerts();

    return {
      day: this.day,
      date: currentDate.toISOString().split('T')[0],
      events: dailyEvents,
      alerts,
      summary: this._generateDailySummary()
    };
  }

  /**
   * Simulate multiple days
   */
  simulatePeriod(days) {
    const results = [];
    for (let i = 0; i < days; i++) {
      results.push(this.simulateDay());
    }
    return results;
  }

  /**
   * Get current ecosystem state
   */
  getState() {
    const companies = [];
    for (const [id, company] of this.companies) {
      companies.push({
        id,
        name: company.brandName,
        cash: company.cash,
        health: company.health,
        momentum: company.momentum,
        clientCount: company.clients.length,
        projectCount: company.projects.length,
        alerts: company.alerts.length
      });
    }

    return {
      day: this.day,
      date: new Date(this.startDate.getTime() + this.day * 86400000).toISOString().split('T')[0],
      companies,
      marketConditions: this.marketConditions,
      totalEvents: this.events.length,
      recentEvents: this.events.slice(-10)
    };
  }

  /**
   * Get company-specific state
   */
  getCompanyState(companyId) {
    const company = this.companies.get(companyId);
    if (!company) return null;

    return {
      id: companyId,
      name: company.brandName,
      cash: company.cash,
      health: company.health,
      momentum: company.momentum,
      dailyRevenue: company.dailyRevenue,
      dailyCosts: company.dailyCosts,
      clients: company.clients.length,
      projects: company.projects.length,
      alerts: company.alerts,
      recentEvents: this.events
        .filter(e => e.companyId === companyId)
        .slice(-10)
    };
  }

  // ─── COMPANY SIMULATION ─────────────────────────────────────────

  _simulateCompanyDay(company, date) {
    const events = [];

    // Calculate daily revenue from clients
    const dailyRevenue = this._calculateDailyRevenue(company);
    company.dailyRevenue = dailyRevenue;

    // Calculate daily costs
    const dailyCosts = this._calculateDailyCosts(company);
    company.dailyCosts = dailyCosts;

    // Update cash
    company.cash += dailyRevenue - dailyCosts;
    company.dailyEbitda = dailyRevenue - dailyCosts;

    // Check for events
    const eventChance = Math.random();
    
    // New client win (2% daily chance)
    if (eventChance < 0.02 && company.clients.length < 10) {
      const event = this._generateNewClientEvent(company, date);
      if (event) {
        events.push(event);
        company.clients.push(event.client);
        company.momentum = Math.min(10, company.momentum + 1);
      }
    }

    // Client churn (1% daily chance)
    if (eventChance > 0.99 && company.clients.length > 1) {
      const event = this._generateClientChurnEvent(company, date);
      if (event) {
        events.push(event);
        company.momentum = Math.max(-10, company.momentum - 2);
      }
    }

    // Project milestone (3% daily chance)
    if (eventChance > 0.97 && eventChance < 1.0 && company.projects.length > 0) {
      const event = this._generateProjectMilestoneEvent(company, date);
      if (event) {
        events.push(event);
      }
    }

    // Risk event (0.5% daily chance)
    if (eventChance < 0.005) {
      const event = this._generateRiskEvent(company, date);
      if (event) {
        events.push(event);
        company.health = Math.max(0, company.health - 5);
        company.momentum = Math.max(-10, company.momentum - 1);
      }
    }

    // Update health based on momentum
    company.health = Math.max(0, Math.min(100, 
      company.health + (company.momentum * 0.1)
    ));

    // Decay momentum toward zero
    company.momentum *= 0.95;

    return { events, company: company.id };
  }

  _calculateDailyRevenue(company) {
    let dailyRevenue = 0;

    // Revenue from active clients
    for (const client of company.clients) {
      if (client.status === 'active') {
        const annualRevenue = client.annualContractValue || 0;
        dailyRevenue += annualRevenue / 365;
      }
    }

    // Apply market conditions
    dailyRevenue *= this.marketConditions.growthRate;

    // Apply momentum effect
    dailyRevenue *= (1 + company.momentum * 0.01);

    // Add some randomness (±5%)
    dailyRevenue *= (0.95 + Math.random() * 0.1);

    return dailyRevenue;
  }

  _calculateDailyCosts(company) {
    const financials = company.annualFinancials || [];
    const latest = financials[financials.length - 1];
    
    if (!latest) return 0;

    // Daily operating costs (annual / 365)
    let dailyCosts = latest.operatingCosts / 365;

    // Apply inflation (0.02% daily)
    dailyCosts *= 1.0002;

    // Apply risk level
    dailyCosts *= this.marketConditions.riskLevel;

    // Add some randomness (±3%)
    dailyCosts *= (0.97 + Math.random() * 0.06);

    return dailyCosts;
  }

  // ─── EVENT GENERATION ──────────────────────────────────────────

  _generateNewClientEvent(company, date) {
    const industries = ['Technology', 'Healthcare', 'Finance', 'Manufacturing', 'Retail', 'Energy'];
    const segments = ['middle_market', 'lower_middle_market', 'enterprise', 'growth_company'];
    
    const industry = industries[Math.floor(Math.random() * industries.length)];
    const segment = segments[Math.floor(Math.random() * segments.length)];
    
    // ACV based on company type
    let acv = 50000 + Math.random() * 200000;
    if (company.id === 'kmt') acv = 100000 + Math.random() * 400000;
    if (company.id === 'panteon') acv = 80000 + Math.random() * 250000;

    const client = {
      clientId: `C-${company.id.toUpperCase()}-${Date.now().toString(36)}`,
      companyId: company.id,
      clientName: `${industry} Corp ${Math.floor(Math.random() * 1000)}`,
      industry,
      country: 'United States',
      segment,
      serviceLineId: company.serviceOfferings?.[0]?.id || 'unknown',
      annualContractValue: Math.round(acv),
      status: 'active',
      startDate: date.toISOString().split('T')[0],
      renewalDate: new Date(date.getTime() + 365 * 86400000).toISOString().split('T')[0]
    };

    return {
      type: 'new_client',
      companyId: company.id,
      date: date.toISOString().split('T')[0],
      description: `New client won: ${client.clientName} ($${(acv / 1000).toFixed(0)}K ACV)`,
      client,
      impact: 'positive'
    };
  }

  _generateClientChurnEvent(company, date) {
    // Pick a random active client to churn
    const activeClients = company.clients.filter(c => c.status === 'active');
    if (activeClients.length === 0) return null;

    const churnedClient = activeClients[Math.floor(Math.random() * activeClients.length)];
    churnedClient.status = 'churned';

    return {
      type: 'client_churn',
      companyId: company.id,
      date: date.toISOString().split('T')[0],
      description: `Client churned: ${churnedClient.clientName}`,
      client: churnedClient,
      impact: 'negative'
    };
  }

  _generateProjectMilestoneEvent(company, date) {
    const activeProjects = company.projects.filter(p => p.stage === 'in_delivery');
    if (activeProjects.length === 0) return null;

    const project = activeProjects[Math.floor(Math.random() * activeProjects.length)];
    const milestones = ['Phase 1 Complete', 'Client Review', 'Deliverable Submitted', 'Payment Received'];
    const milestone = milestones[Math.floor(Math.random() * milestones.length)];

    return {
      type: 'project_milestone',
      companyId: company.id,
      date: date.toISOString().split('T')[0],
      description: `Project milestone: ${project.name} - ${milestone}`,
      project,
      milestone,
      impact: 'positive'
    };
  }

  _generateRiskEvent(company, date) {
    const risks = [
      { type: 'delay', description: 'Project delivery delayed', impact: -3 },
      { type: 'quality', description: 'Quality issue identified', impact: -5 },
      { type: 'competitor', description: 'Competitor entered market', impact: -2 },
      { type: 'regulatory', description: 'New regulation impact', impact: -4 },
      { type: 'talent', description: 'Key employee departure', impact: -6 }
    ];

    const risk = risks[Math.floor(Math.random() * risks.length)];

    return {
      type: 'risk_event',
      companyId: company.id,
      date: date.toISOString().split('T')[0],
      description: risk.description,
      risk,
      impact: 'negative'
    };
  }

  // ─── INTERCOMPANY FLOWS ─────────────────────────────────────────

  _executeIntercompanyFlows(date) {
    const events = [];

    for (const transaction of this.intercompanyTransactions) {
      // Execute flow with some randomness (±10%)
      const variance = 0.9 + Math.random() * 0.2;
      const dailyAmount = (transaction.amount / 365) * variance;

      const fromCompany = this.companies.get(transaction.fromCompanyId);
      const toCompany = this.companies.get(transaction.toCompanyId);

      if (fromCompany && toCompany) {
        fromCompany.cash -= dailyAmount;
        toCompany.cash += dailyAmount;

        // Record significant flows (weekly)
        if (this.day % 7 === 0) {
          events.push({
            type: 'intercompany_flow',
            from: transaction.fromCompanyId,
            to: transaction.toCompanyId,
            date: date.toISOString().split('T')[0],
            description: `${transaction.description}: $${(dailyAmount * 7).toFixed(0)} weekly`,
            amount: dailyAmount * 7,
            impact: 'neutral'
          });
        }
      }
    }

    return events;
  }

  // ─── MARKET DYNAMICS ────────────────────────────────────────────

  _updateMarketConditions(date) {
    // Slowly evolve market conditions
    const dayOfYear = Math.floor((date - new Date(date.getFullYear(), 0, 0)) / 86400000);

    // Seasonal effects (Q4 boost, Q1 slowdown)
    const seasonalFactor = Math.sin((dayOfYear / 365) * Math.PI * 2) * 0.1;
    this.marketConditions.growthRate = 1.0 + seasonalFactor;

    // Random market shocks (5% chance)
    if (Math.random() < 0.05) {
      const shock = 0.9 + Math.random() * 0.2;
      this.marketConditions.riskLevel *= shock;
    }

    // Mean revert risk level
    this.marketConditions.riskLevel = 
      this.marketConditions.riskLevel * 0.99 + 1.0 * 0.01;

    // Competition intensity fluctuates
    this.marketConditions.competitionIntensity = 
      0.8 + Math.random() * 0.4;
  }

  _applyCrossCompanyEffects() {
    // When one company does well, others benefit
    const companyArray = Array.from(this.companies.values());
    
    for (const company of companyArray) {
      if (company.momentum > 5) {
        // High momentum companies help others
        for (const other of companyArray) {
          if (other.id !== company.id) {
            other.health = Math.min(100, other.health + 0.1);
          }
        }
      }
      
      if (company.momentum < -5) {
        // Low momentum companies drag others
        for (const other of companyArray) {
          if (other.id !== company.id) {
            other.health = Math.max(0, other.health - 0.05);
          }
        }
      }
    }
  }

  // ─── HISTORY & RECORDING ────────────────────────────────────────

  _recordHistory(date) {
    const snapshot = {
      day: this.day,
      date: date.toISOString().split('T')[0],
      companies: {}
    };

    for (const [id, company] of this.companies) {
      snapshot.companies[id] = {
        cash: company.cash,
        health: company.health,
        momentum: company.momentum,
        clientCount: company.clients.length,
        projectCount: company.projects.length
      };
    }

    this.history.push(snapshot);

    // Keep last 365 days
    if (this.history.length > 365) {
      this.history.shift();
    }
  }

  _generateDailySummary() {
    const companies = Array.from(this.companies.values());
    
    return {
      totalCash: companies.reduce((sum, c) => sum + c.cash, 0),
      avgHealth: companies.reduce((sum, c) => sum + c.health, 0) / companies.length,
      totalClients: companies.reduce((sum, c) => sum + c.clients.length, 0),
      totalProjects: companies.reduce((sum, c) => sum + c.projects.length, 0),
      topPerformer: companies.reduce((best, c) => c.momentum > best.momentum ? c : best).brandName,
      biggestRisk: companies.reduce((worst, c) => c.momentum < worst.momentum ? c : worst).brandName
    };
  }

  _checkAlerts() {
    const alerts = [];

    for (const [id, company] of this.companies) {
      // Cash alert
      if (company.cash < 50000) {
        alerts.push({
          companyId: id,
          type: 'cash_critical',
          severity: 'critical',
          message: `${company.brandName} cash below $50K: $${(company.cash / 1000).toFixed(0)}K`
        });
      }

      // Health alert
      if (company.health < 50) {
        alerts.push({
          companyId: id,
          type: 'health_warning',
          severity: 'warning',
          message: `${company.brandName} health score: ${company.health.toFixed(0)}`
        });
      }

      // Momentum alert
      if (company.momentum < -5) {
        alerts.push({
          companyId: id,
          type: 'momentum_negative',
          severity: 'warning',
          message: `${company.brandName} negative momentum: ${company.momentum.toFixed(1)}`
        });
      }
    }

    return alerts;
  }

  /**
   * Export ecosystem state to JSON
   */
  exportState() {
    const state = {
      lastUpdated: new Date().toISOString(),
      day: this.day,
      marketConditions: this.marketConditions,
      companies: {},
      recentEvents: this.events.slice(-50),
      history: this.history.slice(-30)
    };

    for (const [id, company] of this.companies) {
      state.companies[id] = {
        brandName: company.brandName,
        cash: company.cash,
        health: company.health,
        momentum: company.momentum,
        clients: company.clients,
        projects: company.projects,
        dailyRevenue: company.dailyRevenue,
        dailyCosts: company.dailyCosts
      };
    }

    return state;
  }
}

module.exports = EcosystemEngine;
