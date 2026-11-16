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
assert.match(el('results-notice').innerHTML,/42 NFL games graded/);
assert.match(el('results-notice').innerHTML,/1 pending/);
assert.match(el('results-cards').innerHTML,/16–25–1/,'Cumulative Injury ATS must include Week 9');
assert.match(el('results-cards').innerHTML,/23–18/,'Cumulative Injury totals must include Week 9');
assert.match(el('results-cards').innerHTML,/12–15/,'Baseline cumulative must exclude research Week9');
assert.match(el('week-results').innerHTML,/Week 10/);
assert.match(el('week-results').innerHTML,/Week 9/);
assert.match(el('week-results').innerHTML,/Week 8/);
assert.match(el('week-results').innerHTML,/research baseline/);
assert.match(el('results-details').innerHTML,/MIA @ IND/);
assert.match(el('results-details').innerHTML,/LAC @ BAL/);
assert.match(el('results-details').innerHTML,/Pending/);
assert.match(el('results-details').innerHTML,/uncalibrated/ig);
assert.equal((el('results-details').innerHTML.match(/<tr>/g)||[]).length,43,
  'Full public results must list 43 games, not Week8 only');
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
console.log('PASS: public Results JS renders 43 games, cumulative cards, correct research exclusion, pending MNF and working week/day filters');
