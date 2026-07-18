#!/usr/bin/env node

/**
 * Alien.Inc Living Ecosystem - Simulation Runner
 * 
 * Run the simulation to see the organism evolve.
 * 
 * Usage:
 *   node simulate.js              # Run 1 day
 *   node simulate.js 30           # Run 30 days
 *   node simulate.js 365 --export # Run 1 year and export state
 *   node simulate.js status       # Show current state
 *   node simulate.js company panteon  # Show company state
 */

const EcosystemEngine = require('./ecosystem-engine');
const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
const command = args[0] || '1';
const option = args[1] || null;

// Initialize engine
const engine = new EcosystemEngine();
engine.initialize(path.join(__dirname, '../../data/alieninc-ecosystem.json'));

console.log('');
console.log('╔══════════════════════════════════════════════════════════════════╗');
console.log('║           ALIEN.INC LIVING ECOSYSTEM SIMULATION                ║');
console.log('║         A self-evolving organism of 7 companies               ║');
console.log('╚══════════════════════════════════════════════════════════════════╝');
console.log('');

// Handle commands
if (command === 'status') {
  const state = engine.getState();
  console.log('📊 CURRENT ECOSYSTEM STATE');
  console.log('─'.repeat(60));
  console.log(`Day: ${state.day}`);
  console.log(`Date: ${state.date}`);
  console.log('');
  
  console.log('Companies:');
  state.companies.forEach(c => {
    const healthBar = '█'.repeat(Math.floor(c.health / 10)) + '░'.repeat(10 - Math.floor(c.health / 10));
    console.log(`  ${c.name.padEnd(25)} $${(c.cash / 1000).toFixed(0).padStart(6)}K  [${healthBar}] ${c.health.toFixed(0)}`);
  });
  
  console.log('');
  console.log('Market Conditions:');
  console.log(`  Growth Rate: ${((state.marketConditions.growthRate - 1) * 100).toFixed(2)}%`);
  console.log(`  Risk Level: ${state.marketConditions.riskLevel.toFixed(2)}`);
  
  process.exit(0);
}

if (command === 'company') {
  const companyId = option || 'panteon';
  const state = engine.getCompanyState(companyId);
  
  if (!state) {
    console.error(`Company "${companyId}" not found.`);
    process.exit(1);
  }
  
  console.log(`🏢 ${state.name.toUpperCase()}`);
  console.log('─'.repeat(60));
  console.log(`Cash: $${(state.cash / 1000).toFixed(0)}K`);
  console.log(`Health: ${state.health.toFixed(0)}/100`);
  console.log(`Momentum: ${state.momentum > 0 ? '+' : ''}${state.momentum.toFixed(1)}`);
  console.log(`Daily Revenue: $${(state.dailyRevenue / 1000).toFixed(2)}K`);
  console.log(`Daily Costs: $${(state.dailyCosts / 1000).toFixed(2)}K`);
  console.log(`Clients: ${state.clients}`);
  console.log(`Projects: ${state.projects}`);
  
  if (state.alerts.length > 0) {
    console.log('');
    console.log('⚠️  Alerts:');
    state.alerts.forEach(a => console.log(`  - ${a.message}`));
  }
  
  if (state.recentEvents.length > 0) {
    console.log('');
    console.log('Recent Events:');
    state.recentEvents.slice(-5).forEach(e => {
      const icon = e.impact === 'positive' ? '🟢' : e.impact === 'negative' ? '🔴' : '🔵';
      console.log(`  ${icon} ${e.date}: ${e.description}`);
    });
  }
  
  process.exit(0);
}

// Run simulation
const days = parseInt(command) || 1;
console.log(`🚀 Simulating ${days} day${days > 1 ? 's' : ''}...`);
console.log('');

const startTime = Date.now();
const results = engine.simulatePeriod(days);
const elapsed = Date.now() - startTime;

// Display results
console.log(`✅ Simulation complete in ${elapsed}ms`);
console.log('');

// Show summary
const finalState = engine.getState();
console.log('📊 FINAL ECOSYSTEM STATE');
console.log('─'.repeat(60));
console.log(`Day: ${finalState.day}`);
console.log(`Date: ${finalState.date}`);
console.log('');

// Company summary table
console.log('Company                    Cash       Health  Momentum  Clients');
console.log('─'.repeat(70));

finalState.companies.forEach(c => {
  const name = c.name.padEnd(25);
  const cash = `$${(c.cash / 1000).toFixed(0)}K`.padStart(8);
  const health = `${c.health.toFixed(0)}`.padStart(6);
  const momentum = `${c.momentum > 0 ? '+' : ''}${c.momentum.toFixed(1)}`.padStart(8);
  const clients = `${c.clients}`.padStart(7);
  console.log(`${name} ${cash}  ${health}  ${momentum}  ${clients}`);
});

console.log('');

// Event summary
const eventCounts = {};
results.forEach(r => {
  r.events.forEach(e => {
    eventCounts[e.type] = (eventCounts[e.type] || 0) + 1;
  });
});

if (Object.keys(eventCounts).length > 0) {
  console.log('📈 Events Generated:');
  Object.entries(eventCounts).forEach(([type, count]) => {
    console.log(`  ${type}: ${count}`);
  });
}

// Alert summary
const allAlerts = results.flatMap(r => r.alerts);
if (allAlerts.length > 0) {
  console.log('');
  console.log('⚠️  Alerts:');
  allAlerts.forEach(a => {
    console.log(`  [${a.severity.toUpperCase()}] ${a.message}`);
  });
}

// Daily summary (last day)
const lastDay = results[results.length - 1];
if (lastDay) {
  console.log('');
  console.log('📊 Last Day Summary:');
  console.log(`  Total Cash: $${(lastDay.summary.totalCash / 1000000).toFixed(2)}M`);
  console.log(`  Avg Health: ${lastDay.summary.avgHealth.toFixed(0)}`);
  console.log(`  Total Clients: ${lastDay.summary.totalClients}`);
  console.log(`  Top Performer: ${lastDay.summary.topPerformer}`);
  console.log(`  Biggest Risk: ${lastDay.summary.biggestRisk}`);
}

// Export if requested
if (option === '--export' || args.includes('--export')) {
  const exportPath = path.join(__dirname, '../../data/ecosystem-state.json');
  const state = engine.exportState();
  fs.writeFileSync(exportPath, JSON.stringify(state, null, 2));
  console.log('');
  console.log(`💾 State exported to: ${exportPath}`);
}

console.log('');
console.log('═'.repeat(60));
console.log('The organism continues to evolve...');
console.log('═'.repeat(60));
console.log('');
