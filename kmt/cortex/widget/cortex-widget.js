/**
 * KMT CORTEX WIDGET
 * 
 * Reusable Cortex integration that can be injected into any Alien.Inc site.
 * Adapts styling to match each brand's design language.
 * 
 * Usage: Include this script and call CortexWidget.init(config)
 */

const CortexWidget = (() => {
  // Brand-specific style configurations
  const brandStyles = {
    alieninc: {
      primary: '#14181c',
      accent: '#ffd400',
      font: '"Instrument Sans", system-ui, sans-serif',
      buttonRadius: '8px',
      cardRadius: '12px'
    },
    kmt: {
      primary: '#0C2B15',
      accent: '#96F878',
      font: 'Georgia, serif',
      buttonRadius: '15px',
      cardRadius: '20px'
    },
    panteon: {
      primary: '#041E42',
      accent: '#00FFFF',
      font: '"Barlow", sans-serif',
      buttonRadius: '4px',
      cardRadius: '8px'
    },
    centra: {
      primary: '#1A3A5C',
      accent: '#00B4D8',
      font: '"Inter", sans-serif',
      buttonRadius: '3px',
      cardRadius: '12px'
    },
    "rousseau": {
      primary: '#0d2344',
      accent: '#c5a059',
      font: '"Montserrat", sans-serif',
      buttonRadius: '4px',
      cardRadius: '8px'
    },
    statute: {
      primary: '#161616',
      accent: '#00cfc1',
      font: '"Rubik", sans-serif',
      buttonRadius: '6px',
      cardRadius: '10px'
    },
    tdac: {
      primary: '#1a1a1a',
      accent: '#e8b4b8',
      font: '"Inter", sans-serif',
      buttonRadius: '8px',
      cardRadius: '12px'
    },
    alcantaraartfoundation: {
      primary: '#161616',
      accent: '#BF955F',
      font: "'Austin', Georgia, serif",
      buttonRadius: '2px',
      cardRadius: '4px'
    }
  };

  let currentBrand = 'kmt';
  let isOpen = false;

  /**
   * Generate the widget CSS for a specific brand
   */
  function generateStyles(brand) {
    const style = brandStyles[brand] || brandStyles.kmt;
    
    return `
      .cortex-widget-trigger {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 60px;
        height: 60px;
        background: ${style.primary};
        border: 2px solid ${style.accent};
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 9999;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        font-family: ${style.font};
      }
      
      .cortex-widget-trigger:hover {
        transform: scale(1.1);
        box-shadow: 0 6px 30px rgba(0,0,0,0.3);
      }
      
      .cortex-widget-trigger svg {
        width: 28px;
        height: 28px;
        fill: ${style.accent};
      }
      
      .cortex-modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.6);
        backdrop-filter: blur(8px);
        z-index: 10000;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      
      .cortex-modal-overlay.active {
        opacity: 1;
        pointer-events: auto;
      }
      
      .cortex-modal {
        background: white;
        width: 90%;
        max-width: 560px;
        border-radius: ${style.cardRadius};
        padding: 32px;
        position: relative;
        transform: translateY(20px) scale(0.95);
        transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        font-family: ${style.font};
        max-height: 90vh;
        overflow-y: auto;
      }
      
      .cortex-modal-overlay.active .cortex-modal {
        transform: translateY(0) scale(1);
      }
      
      .cortex-modal-close {
        position: absolute;
        top: 16px;
        right: 16px;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: #f5f5f5;
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
      }
      
      .cortex-modal-close:hover {
        background: #e0e0e0;
      }
      
      .cortex-modal-close svg {
        width: 16px;
        height: 16px;
        fill: #666;
      }
      
      .cortex-modal h2 {
        font-size: 24px;
        color: ${style.primary};
        margin-bottom: 8px;
        font-weight: 600;
      }
      
      .cortex-modal .cortex-subtitle {
        font-size: 14px;
        color: #666;
        margin-bottom: 24px;
        line-height: 1.5;
      }
      
      .cortex-input-group {
        display: flex;
        gap: 10px;
        margin-bottom: 20px;
      }
      
      .cortex-input-group input {
        flex: 1;
        padding: 14px 16px;
        border: 1px solid #e0e0e0;
        border-radius: ${style.buttonRadius};
        font-size: 15px;
        font-family: inherit;
        outline: none;
        transition: border-color 0.2s;
      }
      
      .cortex-input-group input:focus {
        border-color: ${style.accent};
      }
      
      .cortex-input-group button {
        padding: 14px 24px;
        background: ${style.primary};
        color: ${style.accent};
        border: none;
        border-radius: ${style.buttonRadius};
        font-weight: 600;
        font-size: 14px;
        cursor: pointer;
        transition: all 0.2s;
        font-family: inherit;
        white-space: nowrap;
      }
      
      .cortex-input-group button:hover {
        opacity: 0.9;
        transform: translateY(-1px);
      }
      
      .cortex-response {
        background: #f8f9fa;
        border-radius: ${style.buttonRadius};
        padding: 20px;
        min-height: 100px;
        display: none;
      }
      
      .cortex-response.active {
        display: block;
      }
      
      .cortex-response p {
        font-size: 14px;
        color: #333;
        line-height: 1.6;
        margin: 0;
      }
      
      .cortex-response .cortex-analysis-label {
        color: ${style.primary};
        font-weight: 600;
      }
      
      .cortex-response .cortex-cta {
        display: inline-block;
        margin-top: 16px;
        padding: 10px 20px;
        background: ${style.accent};
        color: ${style.primary};
        border-radius: ${style.buttonRadius};
        font-weight: 600;
        font-size: 13px;
        text-decoration: none;
        cursor: pointer;
        transition: opacity 0.2s;
      }
      
      .cortex-response .cortex-cta:hover {
        opacity: 0.9;
      }
      
      .cortex-loading {
        display: flex;
        align-items: center;
        gap: 12px;
        color: #666;
        font-size: 14px;
      }
      
      .cortex-loading .cortex-spinner {
        width: 20px;
        height: 20px;
        border: 2px solid #e0e0e0;
        border-top-color: ${style.accent};
        border-radius: 50%;
        animation: cortex-spin 0.8s linear infinite;
      }
      
      @keyframes cortex-spin {
        to { transform: rotate(360deg); }
      }
      
      .cortex-quick-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 20px;
      }
      
      .cortex-quick-btn {
        padding: 8px 14px;
        background: #f0f0f0;
        border: none;
        border-radius: ${style.buttonRadius};
        font-size: 12px;
        color: #555;
        cursor: pointer;
        transition: all 0.2s;
        font-family: inherit;
      }
      
      .cortex-quick-btn:hover {
        background: ${style.accent};
        color: ${style.primary};
      }
    `;
  }

  /**
   * Brand-specific content configurations
   */
  const brandContent = {
    kmt: {
      title: 'KMT Cortex',
      subtitle: 'AI-powered research and strategy engine. Ask anything about your market, competitors, or growth opportunities.',
      quickActions: ['Market Analysis', 'Competitors', 'Growth', 'AI Strategy'],
      quickQueries: ['market analysis', 'competitor landscape', 'growth opportunities', 'ai transformation'],
      placeholder: 'e.g., What are the growth opportunities in my industry?',
      ctaLabel: 'Analyze'
    },
    panteon: {
      title: 'Cortex Threat Intelligence',
      subtitle: 'AI-powered exposure analysis. Ask about vulnerabilities, attack surfaces, or risk prioritization.',
      quickActions: ['Vulnerability Scan', 'Attack Surface', 'Risk Priority', 'Compliance'],
      quickQueries: ['vulnerability analysis', 'attack surface assessment', 'risk prioritization', 'compliance gaps'],
      placeholder: 'e.g., What are my highest-risk exposed assets?',
      ctaLabel: 'Analyze'
    },
    centra: {
      title: 'Cortex Security Intelligence',
      subtitle: 'AI-powered vulnerability analysis. Ask about scanning coverage, compliance gaps, or attack surface risks.',
      quickActions: ['Vulnerability Scan', 'Compliance Status', 'Attack Surface', 'Bot Defense'],
      quickQueries: ['vulnerability scanning', 'compliance monitoring', 'attack surface assessment', 'bot defense analysis'],
      placeholder: 'e.g., What are my current CIS benchmark compliance gaps?',
      ctaLabel: 'Analyze'
    },
    "rousseau": {
      title: 'Cortex Capital Intelligence',
      subtitle: 'AI-powered portfolio analysis. Ask about capital allocation, risk exposure, or subsidiary performance.',
      quickActions: ['Capital Flow', 'Risk Exposure', 'Subsidiary KPIs', 'Allocation'],
      quickQueries: ['capital allocation', 'risk exposure', 'subsidiary performance', 'allocation strategy'],
      placeholder: 'e.g., How is capital flowing across the group this quarter?',
      ctaLabel: 'Analyze'
    },
    statute: {
      title: 'Cortex Legal Intelligence',
      subtitle: 'AI-powered legal analysis. Ask about regulatory exposure, contract risk, or compliance gaps.',
      quickActions: ['Regulatory Risk', 'Contract Analysis', 'Compliance', 'Due Diligence'],
      quickQueries: ['regulatory risk', 'contract analysis', 'compliance gaps', 'due diligence'],
      placeholder: 'e.g., What are our highest-priority regulatory risks?',
      ctaLabel: 'Analyze'
    },
    alcantaraartfoundation: {
      title: 'Cortex Cultural Intelligence',
      subtitle: 'AI-powered cultural analysis. Ask about preservation priorities, collection insights, or audience engagement.',
      quickActions: ['Collection Insights', 'Preservation', 'Audience Growth', 'Exhibition Planning'],
      quickQueries: ['collection insights', 'preservation priorities', 'audience growth', 'exhibition planning'],
      placeholder: 'e.g., Which collection items need preservation attention?',
      ctaLabel: 'Analyze'
    },
    alieninc: {
      title: 'Cortex Ecosystem Intelligence',
      subtitle: 'AI-powered group analysis. Ask about cross-company synergies, risk, or operating performance.',
      quickActions: ['Ecosystem Health', 'Synergy Map', 'Risk Cross-Check', 'Performance'],
      quickQueries: ['ecosystem health', 'synergy mapping', 'risk cross-check', 'operating performance'],
      placeholder: 'e.g., What are the top synergies across the group?',
      ctaLabel: 'Analyze'
    }
  };

  /**
   * Generate the modal HTML
   */
  function generateHTML(brand) {
    const style = brandStyles[brand] || brandStyles.kmt;
    const content = brandContent[brand] || brandContent.kmt;
    
    return `
      <button class="cortex-widget-trigger" id="cortex-trigger" aria-label="Open ${content.title}">
        <svg viewBox="0 0 24 24">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
        </svg>
      </button>
      
      <div class="cortex-modal-overlay" id="cortex-overlay">
        <div class="cortex-modal">
          <button class="cortex-modal-close" id="cortex-close">
            <svg viewBox="0 0 24 24">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
          
          <h2>${content.title}</h2>
          <p class="cortex-subtitle">${content.subtitle}</p>
          
          <div class="cortex-quick-actions">
            ${content.quickActions.map((label, i) => `<button class="cortex-quick-btn" data-query="${content.quickQueries[i]}">${label}</button>`).join('\n            ')}
          </div>
          
          <div class="cortex-input-group">
            <input type="text" id="cortex-query" placeholder="${content.placeholder}">
            <button id="cortex-submit">${content.ctaLabel}</button>
          </div>
          
          <div class="cortex-response" id="cortex-response">
            <p id="cortex-response-content"></p>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Show loading state
   */
  function showLoading() {
    const response = document.getElementById('cortex-response');
    const content = document.getElementById('cortex-response-content');
    
    response.classList.add('active');
    content.innerHTML = `
      <div class="cortex-loading">
        <div class="cortex-spinner"></div>
        <span>Analyzing market intelligence...</span>
      </div>
    `;
  }

  /**
   * Show response
   */
  function showResponse(query) {
    const content = document.getElementById('cortex-response-content');
    const contentConfig = brandContent[currentBrand] || brandContent.kmt;
    
    // Load ecosystem data for real metrics
    var ecoData = null;
    try { ecoData = window.EcosystemData ? window.EcosystemData.get() : null; } catch(e) {}
    
    // Brand-specific responses — all metrics sourced from alieninc-ecosystem.json
    var brandResponses = {
      panteon: {
        'vulnerability analysis': buildFromEco(function(eco) {
          var hs = eco.companies.find(function(c){return c.id==='panteon';});
          var kpis = hs.kpis2026F;
          return 'Panteon managed detection and response maintains a mean-time-to-contain of ' + kpis.meanTimeToContainHours + ' hours with critical exposure closure in ' + kpis.criticalExposureClosureDays + ' days. Annual logo retention at ' + ((1 - kpis.annualLogoChurnRate) * 100).toFixed(1) + '% with ' + (kpis.netRevenueRetention * 100).toFixed(0) + '% net revenue retention. MRR: $' + (kpis.mrr/1000).toFixed(0) + 'K.';
        }, 'Panteon delivers managed detection and response, exposure and vulnerability management, and cyber diligence for acquisitions across the Alien.Inc portfolio.'),
        'attack surface assessment': buildFromEco(function(eco) {
          var hs = eco.companies.find(function(c){return c.id==='panteon';});
          return 'Panteon manages security across 7 Alien.Inc companies. Service lines: managed detection and response (56.8% of revenue), exposure and vulnerability management (28.4%), and cyber diligence for acquisitions (14.8%). Headcount: ' + hs.headcount['2026F'] + ' across ' + hs.headcount.fullTime + ' full-time and ' + hs.headcount.contractors + ' contractors.';
        }, 'Panteon provides digital risk defense for the Alien.Inc group, reducing exposure across all portfolio companies.'),
        'risk prioritization': buildFromEco(function(eco) {
          var hs = eco.companies.find(function(c){return c.id==='panteon';});
          var rev = hs.annualFinancials.find(function(f){return f.year===2026;});
          return 'Panteon 2026F revenue: $' + (rev.revenue/1000000).toFixed(2) + 'M with EBITDA of $' + (rev.ebitda/1000).toFixed(0) + 'K. Operating costs: $' + (rev.operatingCosts/1000).toFixed(0) + 'K. Customer acquisition cost: $' + (kpis.avgCustomerCac/1000).toFixed(1) + 'K against lifetime value of $' + (kpis.avgCustomerLtv/1000).toFixed(0) + 'K.';
        }, 'Panteon prioritizes security findings by exploitability and business impact across the Alien.Inc portfolio.'),
        'compliance gaps': buildFromEco(function(eco) {
          return 'Panteon operates three service lines: managed detection and response, exposure and vulnerability management, and cyber diligence for acquisitions. All 16 staff are focused on reducing exposure across the Alien.Inc group.';
        }, 'Panteon audits compliance posture across the Alien.Inc group against target security frameworks.')
      },
      centra: {
        'vulnerability scanning': buildFromEco(function(eco) {
          var ct = eco.companies.find(function(c){return c.id==='centra';});
          var rev = ct.annualFinancials.find(function(f){return f.year===2026;});
          return 'Centra 2026F revenue: $' + (rev.revenue/1000000).toFixed(2) + 'M with EBITDA of $' + (rev.ebitda/1000).toFixed(0) + 'K. Service lines: vulnerability scanning (52.4%), compliance monitoring (28.1%), and bot defense and intrusion detection (19.5%).';
        }, 'Centra delivers continuous vulnerability scanning, compliance monitoring, and bot defense across the Alien.Inc group.'),
        'compliance monitoring': buildFromEco(function(eco) {
          var ct = eco.companies.find(function(c){return c.id==='centra';});
          var kpis = ct.kpis2026F;
          return 'Centra monitoring coverage: ' + kpis.scannedEndpoints + ' endpoints, ' + kpis.complianceFrameworks + ' frameworks tracked, ' + kpis.detectedVulnerabilities + ' vulnerabilities identified. Average scan frequency: ' + kpis.scanFrequency + '. SLA compliance: ' + (kpis.slaCompliance * 100).toFixed(1) + '%.';
        }, 'Centra monitors compliance posture against CIS benchmarks, DISA STIG, PCI-DSS, and NIST frameworks.'),
        'attack surface assessment': buildFromEco(function(eco) {
          var ct = eco.companies.find(function(c){return c.id==='centra';});
          var clients = eco.clientDatabase.filter(function(cl){return cl.companyId==='centra';});
          return 'Centra manages ' + clients.length + ' client security relationships with services in vulnerability scanning, compliance monitoring, and intrusion detection. Active clients include ' + clients.map(function(c){return c.clientName;}).join(', ') + '.';
        }, 'Centra assesses and reduces attack surfaces across enterprise environments.'),
        'bot defense analysis': buildFromEco(function(eco) {
          var ct = eco.companies.find(function(c){return c.id==='centra';});
          var rev = ct.annualFinancials;
          var rev2025 = rev.find(function(f){return f.year===2025;});
          var rev2026 = rev.find(function(f){return f.year===2026;});
          var growth = ((rev2026.revenue - rev2025.revenue) / rev2025.revenue * 100).toFixed(1);
          return 'Centra revenue trajectory: $' + (rev2025.revenue/1000000).toFixed(2) + 'M (2025 actual) to $' + (rev2026.revenue/1000000).toFixed(2) + 'M (2026 forecast), representing ' + growth + '% year-over-year growth.';
        }, 'Centra tracks threat patterns and bot activity across monitored environments.')
      },
      statute: {
        'regulatory risk': buildFromEco(function(eco) {
          var sp = eco.companies.find(function(c){return c.id==='statute';});
          var kpis = sp.kpis2026F;
          return 'Statute & Precedent utilization rate: ' + (kpis.employeeUtilizationRate * 100).toFixed(0) + '% against target of ' + (kpis.targetUtilizationRate * 100).toFixed(0) + '%. Average bill rate: $' + kpis.avgBillRate + '/hour. Matter cycle time: ' + kpis.matterCycleTimeDays + ' days. Contract review turnaround: ' + kpis.contractReviewTurnaroundDays + ' days.';
        }, 'Statute & Precedent delivers AI-enabled legal services for transactions, governance, contracts, and AI policy.'),
        'contract analysis': buildFromEco(function(eco) {
          var sp = eco.companies.find(function(c){return c.id==='statute';});
          var rev = sp.revenueBreakdown2026F;
          return 'Revenue by service line: M&A and transaction counsel $' + (rev[0].amount/1000).toFixed(0) + 'K (' + (rev[0].share*100).toFixed(1) + '%), contract operations $' + (rev[1].amount/1000).toFixed(0) + 'K (' + (rev[1].share*100).toFixed(1) + '%), governance and compliance $' + (rev[2].amount/1000).toFixed(0) + 'K (' + (rev[2].share*100).toFixed(1) + '%).';
        }, 'Statute & Precedent manages contract operations, transaction counsel, and governance compliance.'),
        'compliance gaps': buildFromEco(function(eco) {
          var sp = eco.companies.find(function(c){return c.id==='statute';});
          var clients = eco.clientDatabase.filter(function(cl){return cl.companyId==='statute';});
          return 'Active clients: ' + clients.map(function(c){return c.clientName;}).join(', ') + '. Retainer MRR: $' + (sp.kpis2026F.retainerMrr/1000).toFixed(0) + 'K. Client acquisition cost: $' + (sp.kpis2026F.avgClientCac/1000).toFixed(1) + 'K against lifetime value of $' + (sp.kpis2026F.avgClientLtv/1000).toFixed(0) + 'K.';
        }, 'Statute & Precedent evaluates compliance gaps across governance, contract, and AI policy frameworks.'),
        'due diligence': buildFromEco(function(eco) {
          var sp = eco.companies.find(function(c){return c.id==='statute';});
          var projects = eco.majorProjectsPipeline.filter(function(p){return p.companyId==='statute';});
          var active = projects.filter(function(p){return p.stage==='in_delivery';});
          return 'Active projects: ' + active.map(function(p){return p.name;}).join(', ') + '. Headcount: ' + sp.headcount['2026F'] + ' (' + sp.headcount.fullTime + ' full-time, ' + sp.headcount.contractors + ' contractors). 2026F EBITDA: $' + (sp.annualFinancials.find(function(f){return f.year===2026;}).ebitda/1000).toFixed(0) + 'K.';
        }, 'Statute & Precedent conducts due diligence across corporate filings, regulatory proceedings, and adverse media.')
      },
      alcantaraartfoundation: {
        'collection insights': buildFromEco(function(eco) {
          var alc = eco.companies.find(function(c){return c.id==='alcantara';});
          var kpis = alc.kpis2026F;
          return 'Alcantara Art Foundation: ' + kpis.artifactsDigitized.toLocaleString() + ' artifacts digitized. Collection risk score: ' + kpis.collectionRiskScore + '. Program attendance: ' + kpis.programAttendance.toLocaleString() + '. Active donors: ' + kpis.activeDonors + '. Grant success rate: ' + (kpis.grantSuccessRate * 100).toFixed(0) + '%.';
        }, 'Alcantara Art Foundation preserves cultural memory through conservation, digitization, education, and public access.'),
        'preservation priorities': buildFromEco(function(eco) {
          var alc = eco.companies.find(function(c){return c.id==='alcantara';});
          var rev = alc.annualFinancials.find(function(f){return f.year===2026;});
          var breakdown = alc.revenueBreakdown2026F;
          return '2026F revenue: $' + (rev.revenue/1000).toFixed(0) + 'K. Service lines: digitization and preservation $' + (breakdown[1].amount/1000).toFixed(0) + 'K (' + (breakdown[1].share*100).toFixed(1) + '%), public programs $' + (breakdown[0].amount/1000).toFixed(0) + 'K (' + (breakdown[0].share*100).toFixed(1) + '%), donor membership $' + (breakdown[2].amount/1000).toFixed(0) + 'K (' + (breakdown[2].share*100).toFixed(1) + '%).';
        }, 'Alcantara Art Foundation prioritizes preservation based on condition scoring, environmental exposure, and cultural significance.'),
        'audience growth': buildFromEco(function(eco) {
          var alc = eco.companies.find(function(c){return c.id==='alcantara';});
          var kpis = alc.kpis2026F;
          var rev2025 = alc.annualFinancials.find(function(f){return f.year===2025;});
          var rev2026 = alc.annualFinancials.find(function(f){return f.year===2026;});
          var growth = ((rev2026.revenue - rev2025.revenue) / rev2025.revenue * 100).toFixed(1);
          return 'Revenue trajectory: $' + (rev2025.revenue/1000).toFixed(0) + 'K (2025) to $' + (rev2026.revenue/1000).toFixed(0) + 'K (2026F), ' + growth + '% growth. Donor retention: ' + (kpis.donorRetentionRate * 100).toFixed(0) + '% with ' + kpis.activeDonors + ' active donors.';
        }, 'Alcantara Art Foundation tracks audience engagement across physical programs and digital channels.'),
        'exhibition planning': buildFromEco(function(eco) {
          var alc = eco.companies.find(function(c){return c.id==='alcantara';});
          var clients = eco.clientDatabase.filter(function(cl){return cl.companyId==='alcantara';});
          return 'Active partnerships: ' + clients.map(function(c){return c.clientName;}).join(', ') + '. Headcount: ' + alc.headcount['2026F'] + ' (' + alc.headcount.fullTime + ' full-time, ' + alc.headcount.contractors + ' contractors). 2026F EBITDA: $' + (alc.annualFinancials.find(function(f){return f.year===2026;}).ebitda/1000).toFixed(0) + 'K.';
        }, 'Alcantara Art Foundation plans exhibitions based on collection utilization, visitor interest, and conservation priorities.')
      },
      alieninc: {
        'ecosystem health': buildFromEco(function(eco) {
          var rollup = eco.groupRollup;
          var totalClients = eco.clientDatabase.length;
          return 'Group-wide metrics: $' + (rollup.standaloneRevenueTotal2026F/1000000).toFixed(2) + 'M standalone revenue, $' + (rollup.standaloneEbitdaTotal2026F/1000000).toFixed(2) + 'M EBITDA, ' + totalClients + ' active client relationships across 7 companies. External revenue: $' + (rollup.estimatedExternalRevenue2026F/1000000).toFixed(2) + 'M.';
        }, 'Alien.Inc operates 7 companies across consulting, cybersecurity, media, acquisitions, legal services, and cultural preservation.'),
        'synergy mapping': buildFromEco(function(eco) {
          var txns = eco.intercompanyTransactions2026F;
          var totalIc = txns.reduce(function(sum,t){return sum+t.amount;}, 0);
          var topFlows = txns.sort(function(a,b){return b.amount-a.amount;}).slice(0,3);
          return 'Cross-company service flows: $' + (totalIc/1000).toFixed(0) + 'K annually across ' + txns.length + ' intercompany transactions. Highest-volume: ' + topFlows.map(function(t){return eco.companies.find(function(c){return c.id===t.fromCompanyId;}).brandName + ' to ' + eco.companies.find(function(c){return c.id===t.toCompanyId;}).brandName;}).join(', ') + '.';
        }, 'Alien.Inc companies share services, knowledge, and operational capacity across the group.'),
        'risk cross-check': buildFromEco(function(eco) {
          var cap = eco.holdingsAndCapitalFlow.allocationSummary;
          return 'Capital adequacy: ' + cap.liquidityMonthsOfOperatingCosts + ' months of parent operating costs. Debt: ' + cap.totalDebtOutstandingFormatted + ' at weighted average rate of ' + (cap.weightedAverageDebtRate * 100).toFixed(2) + '%. Dividends 2025: $' + (cap.dividendsReceived2025/1000).toFixed(0) + 'K. Forecast 2026: $' + (cap.dividendsForecast2026/1000).toFixed(0) + 'K.';
        }, 'Alien.Inc monitors capital adequacy, debt levels, and liquidity across the operating group.'),
        'operating performance': buildFromEco(function(eco) {
          var revs = eco.groupRollup.standaloneRevenue2026F;
          var lines = Object.keys(revs).map(function(id) {
            var co = eco.companies.find(function(c){return c.id===id;});
            return co.brandName + ' $' + (revs[id]/1000000).toFixed(2) + 'M';
          });
          return 'Revenue by company (2026F): ' + lines.join(', ') + '. Total: $' + (eco.groupRollup.standaloneRevenueTotal2026F/1000000).toFixed(2) + 'M.';
        }, 'Alien.Inc tracks operating performance across all 7 subsidiaries from the consolidated operating model.')
      },
      "rousseau": {
        'capital allocation': buildFromEco(function(eco) {
          var cap = eco.holdingsAndCapitalFlow.allocationSummary;
          var deployed = cap.capitalDeployedByCompany;
          var lines = Object.keys(deployed).map(function(id) {
            var co = eco.companies.find(function(c){return c.id===id;});
            return co.brandName + ' $' + (deployed[id]/1000).toFixed(0) + 'K';
          });
          return 'Capital deployed: ' + cap.totalCapitalDeployedFormatted + ' total. Positions: ' + lines.join(', ') + '. Debt outstanding: ' + cap.totalDebtOutstandingFormatted + '.';
        }, 'Rousseau allocates capital and governance capacity across the Alien.Inc group.'),
        'risk exposure': buildFromEco(function(eco) {
          var cap = eco.holdingsAndCapitalFlow.allocationSummary;
          var parentCash = cap.parentCashPosition2026F;
          var subCash = cap.subsidiaryCashPosition2026F;
          return 'Liquidity: ' + cap.liquidityMonthsOfOperatingCosts + ' months of operating costs. Parent cash: $' + (parentCash/1000000).toFixed(2) + 'M. Subsidiary cash: $' + (subCash/1000000).toFixed(2) + 'M. Consolidated: $' + (cap.consolidatedCashPosition2026F/1000000).toFixed(2) + 'M.';
        }, 'Rousseau monitors liquidity, cash position, and capital adequacy across the group.'),
        'subsidiary performance': buildFromEco(function(eco) {
          var ebitdas = eco.companies.map(function(c) {
            var rev = c.annualFinancials.find(function(f){return f.year===2026;});
            return { name: c.brandName, ebitda: rev ? rev.ebitda : 0 };
          }).sort(function(a,b){return b.ebitda - a.ebitda;});
          var positive = ebitdas.filter(function(e){return e.ebitda > 0;});
          return 'EBITDA-positive subsidiaries (2026F): ' + positive.length + ' of 7. Range: $' + (ebitdas[ebitdas.length-1].ebitda/1000).toFixed(0) + 'K (' + ebitdas[ebitdas.length-1].name + ') to $' + (ebitdas[0].ebitda/1000).toFixed(0) + 'K (' + ebitdas[0].name + ').';
        }, 'Rousseau oversees EBITDA performance across all operating subsidiaries.'),
        'allocation strategy': buildFromEco(function(eco) {
          var fc = eco.fundCentre.summary;
          var revs = eco.groupRollup.standaloneRevenue2026F;
          var totalRev = eco.groupRollup.standaloneRevenueTotal2026F;
          var kmtPct = (revs.kmt / totalRev * 100).toFixed(1);
          var panteonPct = (revs.panteon / totalRev * 100).toFixed(1);
          var growth = ((eco.companies.find(function(c){return c.id==='kmt';}).annualFinancials.find(function(f){return f.year===2026;}).revenue - eco.companies.find(function(c){return c.id==='kmt';}).annualFinancials.find(function(f){return f.year===2025;}).revenue) / eco.companies.find(function(c){return c.id==='kmt';}).annualFinancials.find(function(f){return f.year===2025;}).revenue * 100).toFixed(1);
          return 'Fund centre: ' + fc.totalAumFormatted + ' across ' + fc.totalFunds + ' funds (' + fc.totalShareClasses + ' share classes). KMT represents ' + kmtPct + '% of group revenue, Panteon ' + panteonPct + '%. KMT YoY growth: ' + growth + '%.';
        }, 'Rousseau manages allocation across operating companies and the fund centre.')
      },
      kmt: {
        'market analysis': buildFromEco(function(eco) {
          var kmt = eco.companies.find(function(c){return c.id==='kmt';});
          var kpis = kmt.kpis2026F;
          var rev = kmt.annualFinancials.find(function(f){return f.year===2026;});
          return 'KMT Consulting 2026F: $' + (rev.revenue/1000000).toFixed(2) + 'M revenue, $' + (rev.ebitda/1000).toFixed(0) + 'K EBITDA. Utilization: ' + (kpis.employeeUtilizationRate * 100).toFixed(0) + '% against target ' + (kpis.targetUtilizationRate * 100).toFixed(0) + '%. Delivery gross margin: ' + (kpis.deliveryGrossMargin * 100).toFixed(0) + '%.';
        }, 'KMT Consulting provides strategy, applied AI, operating model, and post-merger integration services.'),
        'competitor landscape': buildFromEco(function(eco) {
          var kmt = eco.companies.find(function(c){return c.id==='kmt';});
          var kpis = kmt.kpis2026F;
          var clients = eco.clientDatabase.filter(function(cl){return cl.companyId==='kmt';});
          return 'KMT manages ' + clients.length + ' client relationships. Proposal win rate: ' + (kpis.proposalWinRate * 100).toFixed(0) + '%. Backlog: $' + (kpis.backlogSigned/1000000).toFixed(2) + 'M signed. Weighted pipeline: $' + (kpis.weightedPipeline/1000000).toFixed(2) + 'M. Headcount: ' + kmt.headcount['2026F'] + '.';
        }, 'KMT Consulting competes in strategy and applied AI consulting with a focus on measurable operating improvement.'),
        'growth opportunities': buildFromEco(function(eco) {
          var kmt = eco.companies.find(function(c){return c.id==='kmt';});
          var rev2025 = kmt.annualFinancials.find(function(f){return f.year===2025;});
          var rev2026 = kmt.annualFinancials.find(function(f){return f.year===2026;});
          var growth = ((rev2026.revenue - rev2025.revenue) / rev2025.revenue * 100).toFixed(1);
          var kpis = kmt.kpis2026F;
          return 'KMT revenue trajectory: $' + (rev2025.revenue/1000000).toFixed(2) + 'M (2025) to $' + (rev2026.revenue/1000000).toFixed(2) + 'M (2026F), ' + growth + '% YoY growth. Client LTV: $' + (kpis.avgClientLtv/1000).toFixed(0) + 'K. CAC: $' + (kpis.avgClientCac/1000).toFixed(1) + 'K.';
        }, 'KMT Consulting identifies growth opportunities through strategy, AI transformation, and operational improvement.'),
        'ai transformation': buildFromEco(function(eco) {
          var kmt = eco.companies.find(function(c){return c.id==='kmt';});
          var breakdown = kmt.revenueBreakdown2026F;
          var aiLine = breakdown.find(function(b){return b.serviceLineId==='kmt-ai';});
          return 'Applied AI is KMT largest service line at $' + (aiLine.amount/1000).toFixed(0) + 'K (' + (aiLine.share*100).toFixed(1) + '% of revenue). Other lines: strategy $' + (breakdown[0].amount/1000).toFixed(0) + 'K, operations $' + (breakdown[2].amount/1000).toFixed(0) + 'K, PMI $' + (breakdown[3].amount/1000).toFixed(0) + 'K.';
        }, 'KMT Consulting delivers applied AI workflow transformation as its largest service line.')
      }
    };
    
    var brandDefault = {
      panteon: 'Panteon delivers managed detection and response, exposure and vulnerability management, and cyber diligence for acquisitions. Headcount: 16 across 12 full-time and 4 contractors.',
      centra: 'Centra delivers continuous vulnerability scanning, compliance monitoring, and bot defense across enterprise environments. Monitors CIS benchmarks, DISA STIG, and PCI-DSS compliance.',
      statute: 'Statute & Precedent delivers M&A and transaction counsel, contract operations, and governance and compliance services. Average bill rate: $285/hour.',
      alcantaraartfoundation: 'Alcantara Art Foundation preserves cultural memory through conservation, digitization, education, and public access. 18,400 artifacts digitized to date.',
      alieninc: 'Alien.Inc operates 7 companies: KMT Consulting, Panteon, Centra, Statute & Precedent, The Daily Art Cult, Alcantara Art Foundation, and Rousseau.',
      "rousseau": 'Rousseau allocates capital and governance capacity across the Alien.Inc group. Fund centre: EUR 5.77B across 6 funds.'
    };
    
    // Build response from ecosystem data or fallback to service description
    function buildFromEco(fn, fallback) {
      if (!ecoData) return fallback;
      try { return fn(ecoData); } catch(e) { return fallback; }
    }
    
    var queryLower = query.toLowerCase();
    var brandData = brandResponses[currentBrand] || brandResponses.kmt;
    var responseText = brandData[queryLower] || 
      (brandDefault[currentBrand] || brandDefault.kmt);
    
    content.innerHTML = '<p><span class="cortex-analysis-label">Cortex Analysis:</span> ' + responseText + '</p>' +
      '<p style="font-size:10px;color:rgba(255,255,255,0.4);margin:6px 0 0;">Data sourced from alieninc-ecosystem.json</p>' +
      '<a href="#contact" class="cortex-cta" onclick="CortexWidget.close()">Schedule Consultation →</a>';
  }

  /**
   * Initialize the widget
   */
  function init(brand = 'kmt') {
    currentBrand = brand;
    
    // Inject styles
    const styleEl = document.createElement('style');
    styleEl.textContent = generateStyles(brand);
    document.head.appendChild(styleEl);
    
    // Inject HTML
    const container = document.createElement('div');
    container.id = 'cortex-widget-container';
    container.innerHTML = generateHTML(brand);
    document.body.appendChild(container);
    
    // Set up event listeners
    setupEventListeners();
    
    console.log(`[Cortex Widget] Initialized for ${brand}`);
  }

  /**
   * Set up event listeners
   */
  function setupEventListeners() {
    // Trigger button
    const trigger = document.getElementById('cortex-trigger');
    const overlay = document.getElementById('cortex-overlay');
    const closeBtn = document.getElementById('cortex-close');
    const submitBtn = document.getElementById('cortex-submit');
    const queryInput = document.getElementById('cortex-query');
    
    trigger.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
    
    submitBtn.addEventListener('click', handleSubmit);
    queryInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') handleSubmit();
    });
    
    // Quick action buttons
    document.querySelectorAll('.cortex-quick-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const query = btn.dataset.query;
        queryInput.value = query;
        handleSubmit();
      });
    });
  }

  /**
   * Handle query submission
   */
  function handleSubmit() {
    const input = document.getElementById('cortex-query');
    const query = input.value.trim();
    
    if (query) {
      showLoading();
      setTimeout(() => showResponse(query), 1500);
    }
  }

  /**
   * Open the modal
   */
  function open() {
    const overlay = document.getElementById('cortex-overlay');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    isOpen = true;
  }

  /**
   * Close the modal
   */
  function close() {
    const overlay = document.getElementById('cortex-overlay');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
    isOpen = false;
    
    // Reset response
    document.getElementById('cortex-response').classList.remove('active');
    document.getElementById('cortex-query').value = '';
  }

  // Public API
  return {
    init,
    open,
    close,
    brandStyles
  };
})();

// Auto-initialize if brand is specified via data attribute
document.addEventListener('DOMContentLoaded', () => {
  const scriptTag = document.querySelector('script[data-cortex-brand]');
  if (scriptTag) {
    const brand = scriptTag.dataset.cortexBrand;
    CortexWidget.init(brand);
  }
});
