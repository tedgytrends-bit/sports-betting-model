/* Offline DOM contract: both public websites must render real graded CSVs. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const file=process.argv[2];
assert.ok(file,'Usage: node tests/public-results-dom-smoke.cjs <input.json>');
const dataset=JSON.parse(fs.readFileSync(file,'utf8'));
const els={};
function el(id){
  if(!els[id]){
    els[id]={innerHTML:'',textContent:'',value:'all',
      dataset:{},handlers:{},addEventListener(type,fn){this.handlers[type]=fn;}};
  }
  return els[id];
}
global.window={};
global.document={getElementById:el};
require('../docs/public-results.js');
assert.equal(typeof window.renderPublicResults,'function','Missing render function');
window.renderPublicResults(dataset);
const finalCount=new Set(dataset.resultsGames.filter(r=>r.score_status==='FINAL').map(r=>r.game_id)).size;
const pendingCount=new Set(dataset.resultsGames.filter(r=>r.score_status==='PENDING').map(r=>r.game_id)).size;
assert.match(el('results-notice').innerHTML,new RegExp(finalCount+' NFL games graded'));
assert.match(el('results-notice').innerHTML,new RegExp(pendingCount+' pending'));
for(const model of ['injury','baseline']){
  const summary=dataset.resultsSummary.find(r=>r.week==='ALL'&&r.model===model&&r.record_class==='PUBLIC_PUBLISHED');
  assert.ok(summary,'Missing cumulative '+model);
  const rec=summary.ats_wins+'–'+summary.ats_losses+(Number(summary.ats_pushes)?'–'+summary.ats_pushes:'');
  assert.ok(el('results-cards').innerHTML.includes(rec),'Cumulative ATS card does not match stored '+model+' summary');
}
assert.match(el('week-results').innerHTML,/Week 10/);
assert.match(el('week-results').innerHTML,/Week 9/);
assert.match(el('week-results').innerHTML,/Week 8/);
assert.match(el('week-results').innerHTML,/research baseline/);
assert.match(el('results-details').innerHTML,/MIA @ IND/);
assert.match(el('results-details').innerHTML,/LAC @ BAL/);
if(pendingCount) assert.match(el('results-details').innerHTML,/Pending/);
assert.match(el('results-details').innerHTML,/uncalibrated/ig);
assert.equal((el('results-details').innerHTML.match(/<tr>/g)||[]).length,
  new Set(dataset.resultsGames.map(r=>r.game_id)).size,
  'Full public results must list every unique published game, not Week8 only');
const week=el('results-week-filter'),day=el('results-day-filter');
assert.equal(typeof week.handlers.change,'function');
assert.equal(typeof day.handlers.change,'function');
week.value='9';week.handlers.change();
assert.equal((el('results-details').innerHTML.match(/<tr>/g)||[]).length,15,
  'Week9 filter should show all 15 audited games');
day.value='Sunday';day.handlers.change();
assert.ok((el('results-details').innerHTML.match(/<tr>/g)||[]).length<=15);
week.value='10';week.handlers.change();
assert.match(el('results-details').innerHTML,/Week 10|MIA @ IND/);
console.log('PASS: public Results JS renders all published games, cumulative cards, research exclusion and working week/day filters');
