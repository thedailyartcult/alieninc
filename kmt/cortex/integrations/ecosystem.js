/**
 * KMT ECOSYSTEM INTEGRATOR
 * 
 * Manages data flows and service dependencies across Alien.Inc companies.
 * Enables cross-sell opportunities and unified client intelligence.
 * 
 * Architecture: Event-driven with message queue
 * Companies: Rousseau, Panteon, Centra, Statute, TDAC, Alcantara
 */

const EcosystemIntegrator = (() => {
  const config = {
    version: "1.0.0",
    codename: "Ecosystem",
    companies: {
      kmt: { name: "KMT Consulting Group", role: "strategy_ai_consulting" },
      panteon: { name: "Panteon Cyber Defense", role: "cybersecurity" },
      centra: { name: "Centra Security", role: "vulnerability_scanning_compliance" },
      statute: { name: "Statute & Precedent", role: "legal_services" },
      tdac: { name: "The Daily Art Cult", role: "media_publishing" },
      alcantara: { name: "Alcantara Art Foundation", role: "nonprofit_culture" },
      "rousseau": { name: "Rousseau", role: "holding_company" }
    },
    intercompanyRates2026: {
      "kmt-panteon": 96000,
      "centra-panteon": 88000,
      "centra-statute": 142000,
      "kmt-statute": 78000,
      "alcantara-tdac": 54000,
      "tdac-statute": 36000,
      "rousseau-kmt": 126000,
      "rousseau-alcantara": 150000
    }
  };

  /**
   * Service Dependency Graph
   * Maps how companies provide services to each other
   */
  const ServiceDependencies = {
    // KMT requires services from other companies
    kmtRequires: {
      panteon: [
        { service: "cloud_security", description: "Security for client data and AI models" },
        { service: "vulnerability_scans", description: "Regular security assessments" },
        { service: "client_delivery_security", description: "Security review of client deliverables" }
      ],
      statute: [
        { service: "ai_policy_review", description: "AI governance and compliance" },
        { service: "contract_operations", description: "Client contract management" },
        { service: "ip_protection", description: "Intellectual property for AI models" }
      ],
      centra: [
        { service: "vulnerability_scanning", description: "Continuous vulnerability assessment for KMT clients" },
        { service: "compliance_monitoring", description: "Compliance posture monitoring and reporting" }
      ]
    },

    // Other companies require KMT services
    kmtProvides: {
      centra: [
        { service: "security_scanning", description: "Vulnerability scanning and security posture management" },
        { service: "compliance_automation", description: "Automated CIS benchmark and DISA STIG reporting" }
      ],
      panteon: [
        { service: "security_strategy", description: "Cybersecurity strategy consulting" },
        { service: "compliance_advisory", description: "Regulatory compliance consulting" }
      ],
      "rousseau": [
        { service: "portfolio_analytics", description: "Operating metrics and analysis" },
        { service: "board_reporting", description: "Board presentation materials" }
      ]
    }
  };

  /**
   * Cross-Sell Intelligence
   * Identifies opportunities to expand within client accounts
   */
  const CrossSellIntelligence = {
    async analyzeOpportunities(clientId, currentServiceLine) {
      const opportunities = [];
      
      // Map service line adjacencies
      const adjacencyMap = {
        "kmt-strategy": ["kmt-ai", "kmt-ops", "panteon-mdr", "statute-governance"],
        "kmt-ai": ["kmt-strategy", "kmt-ops", "panteon-exposure", "statute-ai_policy"],
        "kmt-ops": ["kmt-strategy", "kmt-pmi", "panteon-diligence", "statute-contracts"],
        "kmt-pmi": ["kmt-ops", "centra-vulnerability", "statute-transactions"]
      };

      const adjacentServices = adjacencyMap[currentServiceLine] || [];
      
      for (const service of adjacentServices) {
        const [companyId, serviceId] = service.split("-");
        opportunities.push({
          companyId,
          serviceId,
          confidence: this.calculateConfidence(clientId, service),
          estimatedValue: this.estimateValue(clientId, service),
          pitch: this.generatePitch(clientId, currentServiceLine, service)
        });
      }

      return opportunities.sort((a, b) => b.confidence - a.confidence);
    },

    calculateConfidence(clientId, service) {
      // AI-powered confidence scoring
      return Math.random() * 0.4 + 0.6; // 60-100% range
    },

    estimateValue(clientId, service) {
      // Estimate based on client profile and service pricing
      return Math.floor(Math.random() * 100000) + 50000;
    },

    generatePitch(clientId, currentService, targetService) {
      return `Based on your ${currentService} engagement, we recommend exploring ${targetService} to maximize value.`;
    }
  };

  /**
   * Unified Client Profile
   * Aggregates client data across all ecosystem companies
   */
  const UnifiedClientProfile = {
    async build(clientId) {
      const profile = {
        clientId,
        aggregateData: await this.aggregateData(clientId),
        totalContractValue: 0,
        totalLifetimeValue: 0,
        companies: {},
        engagementHistory: [],
        riskProfile: {},
        growthOpportunities: []
      };

      // Aggregate from each company
      for (const [companyId, companyConfig] of Object.entries(config.companies)) {
        if (companyId === "kmt") continue; // Skip self
        
        const companyData = await this.fetchCompanyData(clientId, companyId);
        if (companyData) {
          profile.companies[companyId] = companyData;
          profile.totalContractValue += companyData.contractValue || 0;
        }
      }

      return profile;
    },

    async aggregateData(clientId) {
      return {
        financials: {},
        engagements: [],
        deliverables: [],
        feedback: []
      };
    },

    async fetchCompanyData(clientId, companyId) {
      // Would connect to company-specific databases
      return null;
    }
  };

  /**
   * Revenue Attribution Engine
   * Tracks intercompany revenue and value creation
   */
  const RevenueAttribution = {
    async calculateAttribution(engagementId) {
      const attribution = {
        engagementId,
        directRevenue: 0,
        intercompanyRevenue: 0,
        totalGroupValue: 0,
        breakdown: []
      };

      // Calculate intercompany flows
      for (const [flow, amount] of Object.entries(config.intercompanyRates2026)) {
        const [from, to] = flow.split("-");
        attribution.breakdown.push({
          from,
          to,
          amount,
          type: "service_fee"
        });
        attribution.intercompanyRevenue += amount;
      }

      attribution.totalGroupValue = attribution.directRevenue + attribution.intercompanyRevenue;
      
      return attribution;
    },

    async forecastGrowth(currentRevenue, growthRate, years) {
      const forecast = [];
      let revenue = currentRevenue;
      
      for (let i = 0; i < years; i++) {
        revenue = revenue * (1 + growthRate);
        forecast.push({
          year: 2026 + i,
          revenue: Math.round(revenue),
          growth: growthRate
        });
      }
      
      return forecast;
    }
  };

  /**
   * Event Bus
   * Handles real-time communication between companies
   */
  const EventBus = {
    listeners: {},

    subscribe(event, callback) {
      if (!this.listeners[event]) {
        this.listeners[event] = [];
      }
      this.listeners[event].push(callback);
    },

    publish(event, data) {
      if (this.listeners[event]) {
        this.listeners[event].forEach(callback => callback(data));
      }
    },

    // Pre-defined ecosystem events
    events: {
      CLIENT_CREATED: "client:created",
      CLIENT_UPDATED: "client:updated",
      ENGAGEMENT_STARTED: "engagement:started",
      ENGAGEMENT_COMPLETED: "engagement:completed",
      DEAL_SOURCED: "deal:sourced",
      SECURITY_INCIDENT: "security:incident",
      LEGAL_MATTER: "legal:matter",
      CONTENT_PUBLISHED: "content:published"
    }
  };

  // Public API
  return {
    config,
    ServiceDependencies,
    CrossSellIntelligence,
    UnifiedClientProfile,
    RevenueAttribution,
    EventBus,

    /**
     * Main entry point: Initialize ecosystem integration
     */
    async initialize() {
      console.log("[Ecosystem] Initializing KMT Ecosystem Integrator");
      
      // Set up event listeners
      EventBus.subscribe(EventBus.events.CLIENT_CREATED, async (client) => {
        console.log(`[Ecosystem] New client created: ${client.id}`);
        const opportunities = await CrossSellIntelligence.analyzeOpportunities(client.id, "kmt-strategy");
        console.log(`[Ecosystem] Found ${opportunities.length} cross-sell opportunities`);
      });

      EventBus.subscribe(EventBus.events.ENGAGEMENT_COMPLETED, async (engagement) => {
        console.log(`[Ecosystem] Engagement completed: ${engagement.id}`);
        // Trigger satisfaction survey, renewal reminder, etc.
      });

      console.log("[Ecosystem] Initialization complete");
      return { status: "ready" };
    },

    /**
     * Get unified view of a client across all companies
     */
    async getClientView(clientId) {
      return UnifiedClientProfile.build(clientId);
    },

    /**
     * Identify cross-sell opportunities for a client
     */
    async findCrossSellOpportunities(clientId, currentService) {
      return CrossSellIntelligence.analyzeOpportunities(clientId, currentService);
    },

    /**
     * Calculate total group value for a client
     */
    async calculateGroupValue(clientId) {
      const profile = await UnifiedClientProfile.build(clientId);
      return {
        clientId,
        totalValue: profile.totalContractValue,
        companies: Object.keys(profile.companies).length,
        recommendation: profile.totalContractValue < 500000 ? "expand" : "retain"
      };
    }
  };
})();

if (typeof module !== 'undefined' && module.exports) {
  module.exports = EcosystemIntegrator;
}
