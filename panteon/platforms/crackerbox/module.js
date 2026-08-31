// platforms/crackerbox/module.js — Platform module for Crackerbox Intelligence
// Loaded lazily by admin.html platform loader (ensurePlatformModule) on first navigate to one of its pages.
// Pattern keeps admin.html cohesive: shell owns router/auth/topbar, this module owns platform-specific loaders/handlers.
//
// OPERATIONAL RIGOR:
// - Keep this file < 900 lines / 16000 tokens (budget in manifest.json). Split further into pages/ if larger.
// - Do not import other platforms. Use shared/api.js contract (global api()).
// - Register with shell: window.PanteonPlatforms.markLoaded('crackerbox') is called by loader automatically on script load.
// - Export via window.crackerbox or window.PanteonModules['crackerbox'] for debugging.
//
// NEXT STEPS (incremental, no functionality loss):
// 1. Move platform-specific functions from admin.html into this file (e.g. for yono: loadProviders, loadAgents, etc.)
// 2. Keep them as global functions (window.loadProviders = ...) so existing loadPageData switch continues to work.
// 3. After proven in prod with dual fallback (inline + lazy), delete inline duplicates from admin.html.
//
// LLM guidance: read platforms/registry.json + platforms/crackerbox/manifest.json + platforms/crackerbox/pages/*.html + this file ONLY.

(function(){
  console.log('[platform-module] crackerbox loaded (placeholder) — ready for extraction');
  // Example registration hook for health checks:
  if(window.PanteonPlatforms) window.PanteonPlatforms.markLoaded('crackerbox');
  // Attach platform namespace for future handlers:
  window.PanteonModules = window.PanteonModules || {};
  window.PanteonModules['crackerbox'] = {
    id: 'crackerbox',
    version: '1.0.0-placeholder',
    // TODO: move handlers here, e.g.:
    // loadProviders: async function(){ return api('/yono/providers'); }
  };
})();
