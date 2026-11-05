/**
 * KMT Consulting Group - Deliverable Templates Library
 * McKinsey/BCG-grade consulting frameworks and presentation templates
 * 
 * Manages:
 * - Strategy frameworks (Porter's Five Forces, 3H, GE-McKinsey, etc.)
 * - Analysis templates (market sizing, competitive analysis, financial models)
 * - Presentation structures (storyboarding, executive summaries, recommendations)
 * - Deliverable types (decks, reports, memos, models)
 */

class TemplateLibrary {
  constructor() {
    this.templates = new Map();
    this.frameworks = new Map();
    this.presentationStructures = new Map();
    this.analysisTemplates = new Map();
    this._initialized = false;
  }

  initialize() {
    if (this._initialized) return this;
    this._loadTemplates();
    this._loadFrameworks();
    this._loadPresentationStructures();
    this._loadAnalysisTemplates();
    this._initialized = true;
    return this;
  }

  // ─── TEMPLATE MANAGEMENT ────────────────────────────────────────

  getTemplate(templateId) {
    return this.templates.get(templateId) || null;
  }

  getTemplatesByType(type) {
    const results = [];
    for (const [id, template] of this.templates) {
      if (template.type === type) {
        results.push({ id, ...template });
      }
    }
    return results;
  }

  getTemplatesByServiceLine(serviceLine) {
    const results = [];
    for (const [id, template] of this.templates) {
      if (template.serviceLines?.includes(serviceLine)) {
        results.push({ id, ...template });
      }
    }
    return results;
  }

  getTemplatesByComplexity(complexity) {
    const results = [];
    for (const [id, template] of this.templates) {
      if (template.complexity === complexity) {
        results.push({ id, ...template });
      }
    }
    return results;
  }

  // ─── FRAMEWORK ACCESS ───────────────────────────────────────────

  getFramework(frameworkId) {
    return this.frameworks.get(frameworkId) || null;
  }

  getFrameworksByCategory(category) {
    const results = [];
    for (const [id, framework] of this.frameworks) {
      if (framework.category === category) {
        results.push({ id, ...framework });
      }
    }
    return results;
  }

  getRecommendedFrameworks(context) {
    const results = [];
    for (const [id, framework] of this.frameworks) {
      const relevance = this._calculateRelevance(framework, context);
      if (relevance > 0.7) {
        results.push({ id, ...framework, relevance });
      }
    }
    return results.sort((a, b) => b.relevance - a.relevance);
  }

  // ─── PRESENTATION STRUCTURES ────────────────────────────────────

  getPresentationStructure(structureId) {
    return this.presentationStructures.get(structureId) || null;
  }

  getStructuresByDeliverableType(deliverableType) {
    const results = [];
    for (const [id, structure] of this.presentationStructures) {
      if (structure.deliverableType === deliverableType) {
        results.push({ id, ...structure });
      }
    }
    return results;
  }

  // ─── ANALYSIS TEMPLATES ─────────────────────────────────────────

  getAnalysisTemplate(templateId) {
    return this.analysisTemplates.get(templateId) || null;
  }

  getAnalysisByType(type) {
    const results = [];
    for (const [id, template] of this.analysisTemplates) {
      if (template.type === type) {
        results.push({ id, ...template });
      }
    }
    return results;
  }

  // ─── DELIVERABLE GENERATION ─────────────────────────────────────

  createDeliverableOutline(deliverableType, context) {
    const structure = this._getStructureForType(deliverableType);
    if (!structure) return null;

    return {
      type: deliverableType,
      title: context.title || 'Untitled',
      sections: structure.sections.map(section => ({
        name: section.name,
        purpose: section.purpose,
        content: this._generateSectionContent(section, context),
        estimatedLength: section.estimatedLength
      })),
      appendices: structure.appendices || [],
      metadata: {
        createdDate: new Date().toISOString(),
        template: structure.id,
        context
      }
    };
  }

  // ─── PRIVATE HELPERS ─────────────────────────────────────────────

  _loadTemplates() {
    this.templates.clear();
  }

  _loadFrameworks() {
    this.frameworks.clear();
  }

  _loadPresentationStructures() {
    this.presentationStructures.clear();
  }

  _loadAnalysisTemplates() {
    this.analysisTemplates.clear();
  }

  _calculateRelevance(framework, context) {
    let relevance = 0;
    if (framework.applicableTo?.some(item => 
      context.serviceLine?.includes(item) || context.objective?.includes(item)
    )) {
      relevance += 0.5;
    }
    if (framework.complexity === context.complexity) {
      relevance += 0.3;
    }
    if (framework.industry?.includes(context.industry)) {
      relevance += 0.2;
    }
    return Math.min(relevance, 1.0);
  }

  _getStructureForType(deliverableType) {
    for (const [id, structure] of this.presentationStructures) {
      if (structure.deliverableType === deliverableType) {
        return structure;
      }
    }
    return null;
  }

  _generateSectionContent(section, context) {
    return section.placeholder || '';
  }

  _generateId() {
    return 'TPL-' + Date.now().toString(36).toUpperCase() + 
           Math.random().toString(36).substr(2, 4).toUpperCase();
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = TemplateLibrary;
}
