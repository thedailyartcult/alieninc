#!/usr/bin/env node

/**
 * KMT Consulting Group - CLI Interface
 * 
 * Runs the KMT engine from the command line.
 * Usage: node cli.js [companyId] [queryType]
 * 
 * Examples:
 *   node cli.js panteon
 *   node cli.js kmt overview
 *   node cli.js portfolio
 */

const KMTEngine = require('./core/kmt-engine');
const path = require('path');

// Parse command line arguments
const args = process.argv.slice(2);
const companyId = args[0] || 'panteon';
const queryType = args[1] || 'analyze';

// Initialize engine
const engine = new KMTEngine();
engine.initialize(path.join(__dirname, '../data/alieninc-ecosystem.json'));

console.log('='.repeat(80));
console.log('KMT CONSULTING GROUP - AI Consulting Engine');
console.log('='.repeat(80));
console.log('');

try {
  let result;

  switch (queryType) {
    case 'overview':
      result = engine.getCompanyOverview(companyId);
      console.log('\n📋 COMPANY OVERVIEW');
      console.log('-'.repeat(40));
      console.log(JSON.stringify(result, null, 2));
      break;

    case 'portfolio':
      result = engine.getPortfolioOverview();
      console.log('\n🏢 PORTFOLIO OVERVIEW');
      console.log('-'.repeat(40));
      result.forEach(company => {
        console.log(`  ${company.name}: $${(company.revenue / 1000000).toFixed(1)}M revenue, ${company.headcount} employees`);
      });
      break;

    case 'insights':
      result = engine.getCrossCompanyInsights();
      console.log('\n💡 CROSS-COMPANY INSIGHTS');
      console.log('-'.repeat(40));
      console.log(JSON.stringify(result, null, 2));
      break;

    case 'analyze':
    default:
      result = engine.analyze(companyId);
      
      if (result.error) {
        console.error(`\n❌ Error: ${result.error}`);
        process.exit(1);
      }

      // Executive Summary
      console.log('\n📊 EXECUTIVE SUMMARY');
      console.log('-'.repeat(40));
      console.log(`Company: ${result.executiveSummary.companyName}`);
      console.log(`Health Score: ${result.healthScores.overall}/100 (${result.executiveSummary.healthRating})`);
      console.log('');
      
      console.log('Key Findings:');
      result.executiveSummary.keyFindings.forEach((f, i) => {
        console.log(`  ${i + 1}. [${f.severity?.toUpperCase() || 'INFO'}] ${f.finding}`);
      });
      
      console.log('\nTop Recommendations:');
      result.executiveSummary.topRecommendations.forEach(r => {
        console.log(`  ${r.rank}. [${r.priority.toUpperCase()}] ${r.recommendation}`);
        console.log(`     Timeframe: ${r.timeframe}`);
      });
      
      console.log('\nOverall Assessment:');
      console.log(`  ${result.executiveSummary.overallAssessment}`);
      
      // Health Scores
      console.log('\n🏥 HEALTH SCORES');
      console.log('-'.repeat(40));
      console.log(`Financial: ${result.healthScores.financial}/100`);
      console.log(`Operational: ${result.healthScores.operational}/100`);
      console.log(`Overall: ${result.healthScores.overall}/100`);
      
      // Financial Analysis
      if (result.analyses.financial) {
        console.log('\n💰 FINANCIAL ANALYSIS');
        console.log('-'.repeat(40));
        const fin = result.analyses.financial;
        
        console.log(`Revenue: $${(fin.revenueAnalysis.currentRevenue / 1000000).toFixed(1)}M`);
        console.log(`YoY Growth: ${fin.revenueAnalysis.yoyGrowthFormatted}`);
        console.log(`Margin: ${fin.marginAnalysis.currentMarginFormatted}`);
        console.log(`Cash Position: $${(fin.cashAnalysis.cashPosition / 1000).toFixed(0)}K`);
        console.log(`Runway: ${fin.cashAnalysis.monthsRunway || 'N/A'} months`);
        
        if (fin.revenueAnalysis.concentrationRisk !== 'low') {
          console.log(`⚠️  Revenue concentration risk: ${fin.revenueAnalysis.concentrationRisk}`);
        }
      }
      
      // Operational Analysis
      if (result.analyses.operational) {
        console.log('\n⚙️  OPERATIONAL ANALYSIS');
        console.log('-'.repeat(40));
        const ops = result.analyses.operational;
        
        console.log(`Clients: ${ops.clientAnalysis.totalClients} (${ops.clientAnalysis.activeClients} active)`);
        console.log(`Projects: ${ops.deliveryAnalysis.totalProjects}`);
        console.log(`Delivery Health: ${ops.deliveryAnalysis.deliveryHealth}`);
        
        if (ops.clientAnalysis.insights?.length > 0) {
          console.log('\nClient Insights:');
          ops.clientAnalysis.insights.forEach(insight => {
            console.log(`  • ${insight}`);
          });
        }
      }
      
      // Recommendations
      console.log('\n🎯 RECOMMENDATIONS');
      console.log('-'.repeat(40));
      console.log(`Total: ${result.recommendations.totalRecommendations}`);
      console.log(`Quick Wins: ${result.recommendations.summary.quickWinsCount}`);
      
      if (result.recommendations.prioritized.length > 0) {
        console.log('\nPrioritized Actions:');
        result.recommendations.prioritized.slice(0, 5).forEach(rec => {
          console.log(`\n  ${rec.rank}. [${rec.priority.toUpperCase()}] ${rec.recommendation}`);
          console.log(`     Area: ${rec.area}`);
          console.log(`     Timeframe: ${rec.timeframe}`);
          console.log(`     Effort: ${rec.effort}`);
          console.log(`     Impact: ${rec.expectedImpact}`);
        });
      }
      
      // Roadmap
      console.log('\n📅 IMPLEMENTATION ROADMAP');
      console.log('-'.repeat(40));
      
      if (result.recommendations.roadmap.immediate.length > 0) {
        console.log('\nImmediate (0-1 month):');
        result.recommendations.roadmap.immediate.forEach(r => {
          console.log(`  • ${r.recommendation}`);
        });
      }
      
      if (result.recommendations.roadmap.shortTerm.length > 0) {
        console.log('\nShort-term (1-3 months):');
        result.recommendations.roadmap.shortTerm.forEach(r => {
          console.log(`  • ${r.recommendation}`);
        });
      }
      
      if (result.recommendations.roadmap.mediumTerm.length > 0) {
        console.log('\nMedium-term (3-6 months):');
        result.recommendations.roadmap.mediumTerm.forEach(r => {
          console.log(`  • ${r.recommendation}`);
        });
      }
      
      if (result.recommendations.roadmap.longTerm.length > 0) {
        console.log('\nLong-term (6+ months):');
        result.recommendations.roadmap.longTerm.forEach(r => {
          console.log(`  • ${r.recommendation}`);
        });
      }
      
      // Portfolio Context
      console.log('\n🔗 PORTFOLIO CONTEXT');
      console.log('-'.repeat(40));
      console.log(`Portfolio Size: ${result.portfolioContext.portfolioSize} companies`);
      console.log(`Portfolio Revenue: $${(result.portfolioContext.portfolioRevenue / 1000000).toFixed(1)}M`);
      console.log(`Company Share: ${result.portfolioContext.companyShare}`);
      
      if (result.portfolioContext.roleInPortfolio) {
        console.log(`Role: ${result.portfolioContext.roleInPortfolio.primary}`);
        console.log(`Contributions: ${result.portfolioContext.roleInPortfolio.contributions.join(', ')}`);
      }
      
      break;
  }
  
  console.log('\n' + '='.repeat(80));
  console.log('Analysis complete. Data sourced from Alien.Inc ecosystem.');
  console.log('='.repeat(80));
  
} catch (error) {
  console.error(`\n❌ Error: ${error.message}`);
  console.error(error.stack);
  process.exit(1);
}
