/**
 * KMT Consulting Group - Engagement Management System
 * Tracks consulting projects from intake request through delivery
 * 
 * Manages:
 * - Engagement pipeline (stages: Intake → Scoping → Proposal → Active → Delivery → Closed)
 * - Resource allocation across engagements
 * - Status tracking and milestone management
 * - Cross-company visibility (Rousseau oversight)
 * - Performance metrics (utilization, margin, CSAT)
 */

class EngagementEngine {
  constructor() {
    this.engagements = new Map();
    this.pipelines = new Map();
    this.resources = new Map();
    this.milestones = new Map();
    this._initialized = false;
  }

  initialize() {
    if (this._initialized) return this;
    this._loadEngagementData();
    this._initializePipelines();
    this._initializeResources();
    this._initialized = true;
    return this;
  }

  // ─── ENGAGEMENT LIFECYCLE ───────────────────────────────────────

  createEngagement(request) {
    const engagement = {
      id: this._generateId(),
      name: request.name,
      clientCompany: request.clientCompany,
      serviceLine: request.serviceLine,
      priority: request.priority || 'standard',
      status: 'intake',
      stage: 'intake',
      requestedBy: request.requestedBy,
      requestedDate: new Date().toISOString(),
      description: request.description,
      objectives: request.objectives || [],
      estimatedBudget: request.estimatedBudget || null,
      estimatedDuration: request.estimatedDuration || null,
      assignedTeam: [],
      milestones: [],
      deliverables: [],
      risks: [],
      dependencies: [],
      statusUpdates: [{
        date: new Date().toISOString(),
        author: request.requestedBy,
        note: 'Engagement created',
        status: 'intake'
      }],
      metrics: {
        hoursSpent: 0,
        hoursBudgeted: 0,
        burnRate: 0,
        budgetUsed: 0,
        csatScore: null
      }
    };

    this.engagements.set(engagement.id, engagement);
    this._logAudit(engagement.id, 'created', request.requestedBy);
    return engagement;
  }

  advanceStage(engagementId, newStage, notes = '') {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const validTransitions = {
      'intake': ['scoping'],
      'scoping': ['proposal', 'intake'],
      'proposal': ['active', 'scoping'],
      'active': ['delivery', 'on-hold'],
      'delivery': ['closed', 'active'],
      'on-hold': ['active', 'closed'],
      'closed': []
    };

    const allowed = validTransitions[engagement.stage] || [];
    if (!allowed.includes(newStage)) {
      return { error: `Invalid transition: ${engagement.stage} → ${newStage}` };
    }

    engagement.stage = newStage;
    engagement.status = newStage === 'closed' ? 'completed' : newStage;
    engagement.statusUpdates.push({
      date: new Date().toISOString(),
      author: 'system',
      note: notes || `Stage advanced to ${newStage}`,
      status: newStage
    });

    this._logAudit(engagementId, `stage:${newStage}`, 'system');
    return engagement;
  }

  addMilestone(engagementId, milestone) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const milestoneEntry = {
      id: this._generateId(),
      name: milestone.name,
      dueDate: milestone.dueDate,
      owner: milestone.owner,
      status: 'pending',
      deliverables: milestone.deliverables || [],
      notes: milestone.notes || '',
      completedDate: null
    };

    engagement.milestones.push(milestoneEntry);
    this.milestones.set(milestoneEntry.id, { engagementId, milestone: milestoneEntry });
    return milestoneEntry;
  }

  updateMilestone(milestoneId, updates) {
    const tracked = this.milestones.get(milestoneId);
    if (!tracked) return { error: 'Milestone not found' };

    const engagement = this.engagements.get(tracked.engagementId);
    const milestone = engagement.milestones.find(m => m.id === milestoneId);
    
    if (updates.status === 'completed') {
      milestone.status = 'completed';
      milestone.completedDate = new Date().toISOString();
    }
    if (updates.notes) milestone.notes = updates.notes;
    
    return milestone;
  }

  // ─── RESOURCE MANAGEMENT ─────────────────────────────────────────

  assignResource(engagementId, resource) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const assignment = {
      id: this._generateId(),
      name: resource.name,
      role: resource.role,
      allocation: resource.allocation || 100, // percentage
      startDate: resource.startDate || new Date().toISOString(),
      endDate: resource.endDate || null,
      hourlyRate: resource.hourlyRate || 235
    };

    engagement.assignedTeam.push(assignment);
    return assignment;
  }

  getTeamUtilization() {
    const utilization = {};
    for (const [id, engagement] of this.engagements) {
      for (const member of engagement.assignedTeam) {
        if (!utilization[member.name]) {
          utilization[member.name] = { 
            totalAllocation: 0, 
            engagements: [], 
            hoursThisMonth: 0 
          };
        }
        utilization[member.name].totalAllocation += member.allocation;
        utilization[member.name].engagements.push({
          engagementId: id,
          engagementName: engagement.name,
          allocation: member.allocation
        });
      }
    }
    return utilization;
  }

  // ─── BUDGET & TRACKING ──────────────────────────────────────────

  logHours(engagementId, hours, description, date = null) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    engagement.metrics.hoursSpent += hours;
    engagement.metrics.burnRate = engagement.metrics.hoursSpent / 
      Math.max(1, this._daysSinceStart(engagement));
    
    return {
      hoursSpent: engagement.metrics.hoursSpent,
      hoursBudgeted: engagement.metrics.hoursBudgeted,
      utilization: engagement.metrics.hoursBudgeted > 0 
        ? (engagement.metrics.hoursSpent / engagement.metrics.hoursBudgeted * 100).toFixed(1) + '%'
        : 'N/A'
    };
  }

  addBudget(engagementId, budget) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    engagement.metrics.hoursBudgeted = budget.hours || 0;
    engagement.estimatedBudget = budget.total || budget.hours * 235;
    return engagement.metrics;
  }

  // ─── DELIVERABLES ────────────────────────────────────────────────

  addDeliverable(engagementId, deliverable) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const del = {
      id: this._generateId(),
      name: deliverable.name,
      type: deliverable.type, // 'deck', 'report', 'model', 'memo'
      status: 'draft',
      author: deliverable.author,
      createdDate: new Date().toISOString(),
      version: '1.0',
      reviewStatus: 'pending',
      file: deliverable.file || null
    };

    engagement.deliverables.push(del);
    return del;
  }

  updateDeliverable(engagementId, deliverableId, updates) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const del = engagement.deliverables.find(d => d.id === deliverableId);
    if (!del) return { error: 'Deliverable not found' };

    Object.assign(del, updates);
    return del;
  }

  // ─── RISKS & DEPENDENCIES ────────────────────────────────────────

  logRisk(engagementId, risk) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const riskEntry = {
      id: this._generateId(),
      description: risk.description,
      severity: risk.severity || 'medium', // low, medium, high, critical
      likelihood: risk.likelihood || 'medium',
      mitigation: risk.mitigation || '',
      owner: risk.owner,
      status: 'open',
      loggedDate: new Date().toISOString()
    };

    engagement.risks.push(riskEntry);
    return riskEntry;
  }

  addDependency(engagementId, dependency) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return { error: 'Engagement not found' };

    const dep = {
      id: this._generateId(),
      description: dependency.description,
      type: dependency.type || 'external', // internal, external
      owner: dependency.owner,
      dueDate: dependency.dueDate,
      status: 'pending',
      blocks: dependency.blocks || []
    };

    engagement.dependencies.push(dep);
    return dep;
  }

  // ─── REPORTING ──────────────────────────────────────────────────

  getEngagementSummary(engagementId) {
    const engagement = this.engagements.get(engagementId);
    if (!engagement) return null;

    return {
      id: engagement.id,
      name: engagement.name,
      client: engagement.clientCompany,
      serviceLine: engagement.serviceLine,
      stage: engagement.stage,
      health: this._calculateHealth(engagement),
      budget: {
        estimated: engagement.estimatedBudget,
        spent: engagement.metrics.budgetUsed,
        hoursSpent: engagement.metrics.hoursSpent,
        hoursBudgeted: engagement.metrics.hoursBudgeted
      },
      team: engagement.assignedTeam.length,
      milestones: {
        total: engagement.milestones.length,
        completed: engagement.milestones.filter(m => m.status === 'completed').length
      },
      deliverables: {
        total: engagement.deliverables.length,
        delivered: engagement.deliverables.filter(d => d.status === 'delivered').length
      },
      risks: engagement.risks.filter(r => r.status === 'open').length,
      daysSinceStart: this._daysSinceStart(engagement)
    };
  }

  getPipeline() {
    const pipeline = {};
    for (const [id, engagement] of this.engagements) {
      if (!pipeline[engagement.stage]) {
        pipeline[engagement.stage] = [];
      }
      pipeline[engagement.stage].push({
        id,
        name: engagement.name,
        client: engagement.clientCompany,
        serviceLine: engagement.serviceLine,
        priority: engagement.priority,
        health: this._calculateHealth(engagement)
      });
    }
    return pipeline;
  }

  getClientEngagements(clientCompany) {
    const results = [];
    for (const [id, engagement] of this.engagements) {
      if (engagement.clientCompany === clientCompany) {
        results.push(this.getEngagementSummary(id));
      }
    }
    return results;
  }

  getEngagementsByServiceLine(serviceLine) {
    const results = [];
    for (const [id, engagement] of this.engagements) {
      if (engagement.serviceLine === serviceLine) {
        results.push(this.getEngagementSummary(id));
      }
    }
    return results;
  }

  // ─── PRIVATE HELPERS ─────────────────────────────────────────────

  _loadEngagementData() {
    this.engagements.clear();
    // In production, this loads from engagements.json
    // For now, starts with empty engagement store
  }

  _initializePipelines() {
    const stages = ['intake', 'scoping', 'proposal', 'active', 'delivery', 'closed'];
    stages.forEach(stage => this.pipelines.set(stage, []));
  }

  _initializeResources() {
    // Core KMT team roster - populated from ecosystem data
    this.resources.clear();
  }

  _calculateHealth(engagement) {
    let health = 'green';
    
    // Check budget burn
    if (engagement.metrics.hoursBudgeted > 0) {
      const burnRatio = engagement.metrics.hoursSpent / engagement.metrics.hoursBudgeted;
      if (burnRatio > 1.0) health = 'red';
      else if (burnRatio > 0.8) health = 'yellow';
    }

    // Check risks
    const criticalRisks = engagement.risks.filter(r => 
      r.severity === 'critical' && r.status === 'open'
    ).length;
    if (criticalRisks > 0) health = 'red';

    // Check milestone delays
    const overdueMilestones = engagement.milestones.filter(m => 
      m.status !== 'completed' && new Date(m.dueDate) < new Date()
    ).length;
    if (overdueMilestones > 0) health = 'yellow';

    return health;
  }

  _daysSinceStart(engagement) {
    const start = new Date(engagement.requestedDate);
    const now = new Date();
    return Math.floor((now - start) / (1000 * 60 * 60 * 24));
  }

  _logAudit(engagementId, action, user) {
    // Audit trail for compliance - logs to internal audit store
    const entry = {
      engagementId,
      action,
      user,
      timestamp: new Date().toISOString()
    };
    // In production, writes to audit log
    return entry;
  }

  _generateId() {
    return 'ENG-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = EngagementEngine;
}
