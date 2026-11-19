/* Source-backed Results DOM test: mobile-friendly cards, real grades and filters. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=process.argv[2];
assert.ok(path,'Expected source JSON with original and directional records');
const data=JSON.parse(fs.readFileSync(path,'utf8'));
const els={};
function element(id){
  if(!els[id])els[id]={
    innerHTML:'',textContent:'',value:'all',dataset:{},handlers:{},
    addEventListener(k,fn){this.handlers[k]=fn;}
  };
  return els[id];
}
global.window={};
global.document={getElementById:element};
require('../docs/public-results.js');
assert.equal(typeof window.renderPublicResults,'function');
window.renderPublicResults(data);
const overall=data.directionalSummary.find(r=>r.week==='ALL'&&r.model==='injury'&&
    r.record_class==='DERIVED_DIRECTIONAL_TIEBREAK');
assert.ok(overall);
const c=element('results-cards').innerHTML;
const s=kind=>overall[kind+'_wins']+'–'+overall[kind+'_losses']+
    (Number(overall[kind+'_pushes'])?'–'+overall[kind+'_pushes']:'');
assert.ok(c.includes(s('ats')),'ATS overall must match immutable grade source');
assert.ok(c.includes(s('totals')),'Totals overall must match immutable grade source');
assert.equal((c.match(/class="result-overview-card"/g)||[]).length,2);
assert.ok(c.includes('Against the spread')&&c.includes('Game totals'));
assert.ok(!c.includes('BASELINE / ATS'),'Baseline must not be a public Results card');
for(const w of [8,9,10])assert.match(element('week-results').innerHTML,new RegExp('Week '+w));
assert.ok(element('results-game-desc').textContent.includes('games'));
const rows=()=>element('results-details').innerHTML;
const count=()=> (rows().match(/class="result-game-card"/g)||[]).length;
const latestWeek=Math.max(...data.directionalGames.map(r=>Number(r.week)));
assert.equal(element('results-week-filter').value,String(latestWeek),'Most recent week should show first');
assert.equal(count(),data.directionalGames.filter(r=>Number(r.week)===latestWeek).length);
element('results-week-filter').value='10';
element('results-week-filter').handlers.change();
assert.match(rows(),/MIA @ IND/);
assert.match(rows(),/LAC @ BAL/);
assert.match(rows(),/QB value uncalibrated/);
const week=element('results-week-filter'),day=element('results-day-filter');
assert.equal(typeof week.handlers.change,'function');
assert.equal(typeof day.handlers.change,'function');
week.value='8';week.handlers.change();
assert.equal(count(),14,'Week8 should show all original 14 games');
assert.match(rows(),/IND @ JAX/);
assert.match(rows(),/Over 46/);
assert.match(rows(),/Retrospective direction/);
assert.match(rows(),/result-status win/);
week.value='9';week.handlers.change();
assert.equal(count(),15,'Week9 should show all 15 audited results');
day.value='Sunday';day.handlers.change();
assert.ok(count()<=15);
day.value='all';day.handlers.change();
week.value='all';week.handlers.change();
assert.equal(count(),new Set(data.directionalGames.map(x=>x.game_id)).size,
    'All weeks should display every unique matchup');
console.log('PASS: 2 overall Injury cards; mobile game cards; 43 games; original result integrity; week/day filters; disclosed Week8 tiebreak');
