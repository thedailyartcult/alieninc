/**
 * KMT Consulting Group - Methodology Library
 * Consulting playbooks, best practices, and operational tools
 * 
 * Manages:
 * - Engagement playbooks (by service line)
 * - Quality standards and deliverable checklists
 * - Interview guides and research methodologies
 * - Workshop facilitation guides
 * - Best practices repository
 */

class MethodologyLibrary {
  constructor() {
    this.playbooks = new Map();
    this.qualityStandards = new Map();
    this.interviewGuides = new Map();
    this.workshopGuides = new Map();
    this.bestPractices = new Map();
    this._initialized = false;
  }

  initialize() {
    if (this._initialized) return this;
    this._loadPlaybooks();
    this._loadQualityStandards();
    this._loadInterviewGuides();
    this._loadWorkshopGuides();
    this._loadBestPractices();
    this._initialized = true;
    return this;
  }

  // ─── PLAYBOOK ACCESS ────────────────────────────────────────────

  getPlaybook(playbookId) {
    return this.playbooks.get(playbookId) || null;
  }

  getPlaybooksByServiceLine(serviceLine) {
    const results = [];
    for (const [id, playbook] of this.playbooks) {
      if (playbook.serviceLine === serviceLine) {
        results.push({ id, ...playbook });
      }
    }
    return results;
  }

  getPlaybookByPhase(phase) {
    const results = [];
    for (const [id, playbook] of this.playbooks) {
      if (playbook.phases?.some(p => p.name === phase)) {
        results.push({ id, ...playbook });
      }
    }
    return results;
  }

  // ─── QUALITY STANDARDS ──────────────────────────────────────────

  getQualityStandard(standardId) {
    return this.qualityStandards.get(standardId) || null;
  }

  getQualityChecklist(deliverableType) {
    for (const [id, standard] of this.qualityStandards) {
      if (standard.deliverableType === deliverableType) {
        return standard;
      }
    }
    return null;
  }

  // ─── INTERVIEW GUIDES ───────────────────────────────────────────

  getInterviewGuide(guideId) {
    return this.interviewGuides.get(guideId) || null;
  }

  getInterviewGuidesByContext(context) {
    const results = [];
    for (const [id, guide] of this.interviewGuides) {
      if (guide.context === context || guide.context === 'all') {
        results.push({ id, ...guide });
      }
    }
    return results;
  }

  // ─── WORKSHOP GUIDES ────────────────────────────────────────────

  getWorkshopGuide(guideId) {
    return this.workshopGuides.get(guideId) || null;
  }

  getWorkshopGuidesByType(type) {
    const results = [];
    for (const [id, guide] of this.workshopGuides) {
      if (guide.type === type) {
        results.push({ id, ...guide });
      }
    }
    return results;
  }

  // ─── BEST PRACTICES ─────────────────────────────────────────────

  getBestPractice(practiceId) {
    return this.bestPractices.get(practiceId) || null;
  }

  getBestPracticesByCategory(category) {
    const results = [];
    for (const [id, practice] of this.bestPractices) {
      if (practice.category === category) {
        results.push({ id, ...practice });
      }
    }
    return results;
  }

  searchBestPractices(query) {
    const results = [];
    const queryLower = query.toLowerCase();
    for (const [id, practice] of this.bestPractices) {
      if (practice.title.toLowerCase().includes(queryLower) ||
          practice.description.toLowerCase().includes(queryLower) ||
          practice.tags?.some(tag => tag.toLowerCase().includes(queryLower))) {
        results.push({ id, ...practice });
      }
    }
    return results;
  }

  // ─── ENGAGEMENT SUPPORT ─────────────────────────────────────────

  getEngagementToolkit(engagementType) {
    return {
      playbooks: this.getPlaybooksByServiceLine(engagementType),
      qualityChecklist: this.getQualityChecklist(engagementType),
      interviewGuides: this.getInterviewGuidesByContext(engagementType),
      bestPractices: this.getBestPracticesByCategory(engagementType)
    };
  }

  // ─── PRIVATE HELPERS ─────────────────────────────────────────────

  _loadPlaybooks() {
    this.playbooks.clear();
  }

  _loadQualityStandards() {
    this.qualityStandards.clear();
  }

  _loadInterviewGuides() {
    this.interviewGuides.clear();
  }

  _loadWorkshopGuides() {
    this.workshopGuides.clear();
  }

  _loadBestPractices() {
    this.bestPractices.clear();
  }

  _generateId() {
    return 'MTH-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = MethodologyLibrary;
}
