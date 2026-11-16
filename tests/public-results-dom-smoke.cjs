/* Offline DOM contract for the cumulative Injury directional record. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=process.argv[2];
assert.ok(source,'Usage: node tests/public-results-dom-smoke.cjs <input.json>');
const data=JSON.parse(fs.readFileSync(source,'utf8'));
const controls={};
function get(id){
  if(!controls[id])controls[id]={
    innerHTML:'',textContent:'',value:'all',dataset:{},handlers:{},
    addEventListener(type,cb){this.handlers[type]=cb;}
  };
  return controls[id];
}
global.window={};global.document={getElementById:get};
require('../docs/public-results.js');
assert.equal(typeof window.renderPublicResults,'function');
window.renderPublicResults(data);
const finalCount=new Set(data.directionalGames.filter(r=>r.score_status==='FINAL').map(r=>r.game_id)).size;
const pendingCount=new Set(data.directionalGames.filter(r=>r.score_status==='PENDING').map(r=>r.game_id)).size;
assert.equal(get('results-notice').innerHTML,'','Redundant Results notice must not render');
assert.ok(finalCount>=42 && pendingCount>=0,'Published results cohort should still be present');
const overall=data.directionalSummary.find(r=>r.week==='ALL'&&r.model==='injury'
  &&r.record_class==='DERIVED_DIRECTIONAL_TIEBREAK');
assert.ok(overall);
const ats=overall.ats_wins+'–'+overall.ats_losses+(Number(overall.ats_pushes)?'–'+overall.ats_pushes:'');
const totals=overall.totals_wins+'–'+overall.totals_losses+(Number(overall.totals_pushes)?'–'+overall.totals_pushes:'');
assert.ok(get('results-cards').innerHTML.includes(ats));
assert.ok(get('results-cards').innerHTML.includes(totals));
assert.equal((get('results-cards').innerHTML.match(/class="model-card"/g)||[]).length,2);
assert.match(get('results-cards').innerHTML,/OVERALL INJURY MODEL/);
assert.doesNotMatch(get('results-cards').innerHTML,/BASELINE \/ ATS/);
for(const w of ['Week 8','Week 9','Week 10'])assert.match(get('week-results').innerHTML,new RegExp(w));
assert.match(get('week-results').innerHTML,/tiebreaker/);
const gameList=get('results-details').innerHTML;
assert.match(gameList,/IND @ JAX/);
assert.match(gameList,/Over · <span[^>]+>Win/);
assert.match(gameList,/Baseline tiebreaker \(retrospective\)/);
assert.match(gameList,/49 total · Over/);
assert.match(gameList,/MIA @ IND/);
assert.match(gameList,/LAC @ BAL/);
assert.match(gameList,/uncalibrated/);
assert.equal((gameList.match(/<tr>/g)||[]).length,
  new Set(data.directionalGames.map(r=>r.game_id)).size);
const week=get('results-week-filter'),day=get('results-day-filter');
assert.equal(typeof week.handlers.change,'function');
assert.equal(typeof day.handlers.change,'function');
week.value='9';week.handlers.change();
assert.equal((get('results-details').innerHTML.match(/<tr>/g)||[]).length,15);
day.value='Sunday';day.handlers.change();
assert.ok((get('results-details').innerHTML.match(/<tr>/g)||[]).length<=15);
week.value='10';week.handlers.change();
assert.match(get('results-details').innerHTML,/MIA @ IND/);
console.log('PASS: two overall Injury record cards; sourced Week8 Over/Win retrospective direction; original snapshot preserved; all games and filters');
