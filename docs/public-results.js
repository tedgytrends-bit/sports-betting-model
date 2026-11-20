/* Tedgy Trends — simple, read-only Injury model results.
 * This page uses validated frozen source grades and a separately labeled
 * directional tiebreak for the Week 8 exactly-at-market Injury total.
 * It NEVER writes or backfills forecasts in the browser. */
(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g,
    ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const number = value => value === '' || value == null ? NaN : Number(value);
  const n = x => Number.isFinite(number(x)) ? number(x) : 0;
  const classFor = result => result === 'Win' ? 'win' :
      result === 'Loss' ? 'loss' : result === 'Push' ? 'push' : 'pending';
  const grade = result => '<span class="result-status '+classFor(result)+'">'+escape(result)+'</span>';
  const val = value => Number.isFinite(number(value)) ? String(number(value)) : '—';
  const record = (r,category) => {
    const pre = category === 'ats' ? 'ats_' : 'totals_';
    const win = n(r[pre+'wins']), loss=n(r[pre+'losses']), push=n(r[pre+'pushes']);
    return win+'–'+loss+(push?'–'+push:'');
  };

  const state={week:null,day:'all'};
  function verify(raw, summary, directional, adjustedSummary) {
    if(!Array.isArray(raw)||!Array.isArray(summary)||!Array.isArray(directional)
       ||!Array.isArray(adjustedSummary)||directional.length<43)
      throw Error('Results files are missing or incomplete.');
    const unique=new Map();
    for(const x of raw){
      const key=x.game_id+'|'+x.model;
      if(unique.has(key))throw Error('Duplicate published record: '+key);
      unique.set(key,x);
      if(!['FINAL','PENDING'].includes(x.score_status))
        throw Error('Invalid completion status: '+key);
    }
    if(directional.length!==raw.filter(r=>r.model==='injury'&&r.record_class==='PUBLIC_PUBLISHED').length)
      throw Error('Directional games do not match the published Injury cohort.');
    const seen=new Set();
    for(const item of directional){
      if(item.model!=='injury'||item.record_class!=='DERIVED_DIRECTIONAL_TIEBREAK'
         ||seen.has(item.game_id)||!['Over','Under'].includes(item.total_pick)
         ||!['Win','Loss','Push','Pending'].includes(item.total_result))
        throw Error('Invalid or duplicate game in Injury records: '+item.game_id);
      seen.add(item.game_id);
      const original=unique.get(item.game_id+'|injury');
      if(!original||original.record_class!=='PUBLIC_PUBLISHED')
        throw Error('Missing original forecast for '+item.game_id);
      for(const field of ['ats_pick','ats_result','projected_total','bovada_total',
                          'score_status','actual_away','actual_home']){
        if(String(item[field])!==String(original[field]))
          throw Error('Game result or original model value was changed: '+item.game_id);
      }
      if(original.total_result!=='No lean' &&
         (item.total_result!==original.total_result||item.total_pick!==original.total_pick))
        throw Error('Unexpected rewrite of an Injury pick: '+item.game_id);
      if(original.total_result==='No lean' &&
        !['POSTHOC_POLICY_USING_PREEXISTING_PREGAME_BASELINE',
          'PROSPECTIVE_POLICY_EXACT_TWO_MODEL_TIE_UNDER'].includes(item.selection_provenance))
        throw Error('An exact-market fallback lacks a documented source: '+item.game_id);
      if(item.score_status==='FINAL' &&
        (!Number.isInteger(number(item.actual_home))||!Number.isInteger(number(item.actual_away))))
        throw Error('Final score is missing: '+item.game_id);
    }
    const tie=directional.find(r=>r.game_id==='2026_08_IND_JAX');
    if(!tie||tie.total_pick!=='Over'||tie.total_result!=='Win'
      ||tie.fallback_projected_total!=='46.9'
      ||tie.original_total_result!=='No lean')
      throw Error('Week 8 tie-breaker does not match the archived pregame evidence.');
    const overall=adjustedSummary.find(s=>s.week==='ALL'&&s.model==='injury'&&
      s.record_class==='DERIVED_DIRECTIONAL_TIEBREAK');
    if(!overall||n(overall.games_expected)!==directional.length||
       n(overall.games_final)!==directional.filter(r=>r.score_status==='FINAL').length)
      throw Error('Overall record does not reconcile with game-by-game grades.');
    for(const kind of ['ats','totals']){
      for(const [field,label] of [['Win','wins'],['Loss','losses'],['Push','pushes']]){
        if(n(overall[kind+'_'+label])!==directional.filter(r=>r.score_status==='FINAL'&&
          r[(kind==='ats'?'ats_result':'total_result')]===field).length)
          throw Error('Overall '+kind+' record does not match the games.');
      }
    }
    return overall;
  }

  function resultCard(overall,kind){
    const title=kind==='ats'?'Against the spread':'Game totals';
    const key=kind==='ats'?'ats':'totals';
    const percentage=number(overall[key+'_win_pct']);
    const finalCount=n(overall.games_final), pending=n(overall.games_pending);
    return '<div class="result-overview-card">'
      +'<div class="result-overview-label">'+escape(title)+'</div>'
      +'<div class="result-overview-value">'+escape(record(overall,key))+'</div>'
      +'<div class="result-overview-meta">'+(Number.isFinite(percentage)?percentage.toFixed(1)+'% win rate':'')
      +' · '+finalCount+' finished'+(pending?' · '+pending+' pending':'')+'</div></div>';
  }

  function weeklyRows(games,summary){
    const weeks=[...new Set(games.map(x=>Number(x.week)))].sort((a,b)=>b-a);
    $('week-results').innerHTML=weeks.map(week=>{
      const x=summary.find(row=>String(row.week)===String(week)&&
        row.record_class==='DERIVED_DIRECTIONAL_TIEBREAK'&&row.model==='injury');
      if(!x)throw Error('Week '+week+' is missing its official summary.');
      return '<div class="result-week-row">'
        +'<div class="result-week-name"><strong>Week '+week+'</strong><small>'
        +n(x.games_final)+' of '+n(x.games_expected)+' final</small></div>'
        +'<div class="result-week-record"><span>ATS</span><strong>'+escape(record(x,'ats'))+'</strong></div>'
        +'<div class="result-week-record"><span>Totals</span><strong>'+escape(record(x,'totals'))+'</strong></div></div>';
    }).join('');
    $('week-title').textContent='Week-by-week results';
    $('results-desc').textContent='Injury model · 2026 season';
    return weeks;
  }

  function gameCard(item){
    const finished=item.score_status==='FINAL';
    const homeMargin=number(item.home_favored_spread);
    const fav=homeMargin>0 ? item.home_team :
      homeMargin<0 ? item.away_team : 'Pick’em';
    const spread=homeMargin===0?'PK':fav+' -'+val(Math.abs(homeMargin));
    const total=number(item.bovada_total);
    const score=finished
      ?escape(item.away_team)+' '+escape(val(item.actual_away))+'  –  '
         +escape(item.home_team)+' '+escape(val(item.actual_home))
      :'Awaiting final score';
    const fallback=item.selection_provenance==='POSTHOC_POLICY_USING_PREEXISTING_PREGAME_BASELINE';
    const rookie=(item.source_warning||'').includes('NOT CALIBRATED');
    const marketNumber=val(item.bovada_total);
    const atsPick=item.ats_pick==='No lean'?'No recorded direction':item.ats_pick;
    const totalPick=item.total_pick+' '+marketNumber;
    const recordTotal=finished?n(item.actual_home)+n(item.actual_away):null;
    const actualTotal=finished?recordTotal+' points':'—';
    const day=escape(item.day||'');
    return '<article class="result-game-card">'
      +'<div class="result-game-top"><span>WEEK '+escape(item.week)+' · '+day.toUpperCase()
      +'</span>'+grade(finished?'Final':'Pending')+'</div>'
      +'<div class="result-game-score"><strong>'+escape(item.away_team)+' @ '+escape(item.home_team)
      +'</strong><span>'+score+'</span></div>'
      +'<div class="result-market">Bovada: '+escape(spread)+' · Total '+escape(marketNumber)
      +(finished?' · Final '+escape(actualTotal):'')+'</div>'
      +'<div class="result-picks">'
      +'<div><div class="result-pick-title">ATS</div><div class="result-pick-line"><b>'+escape(atsPick)+'</b>'+grade(item.ats_result)+'</div></div>'
      +'<div><div class="result-pick-title">TOTAL</div><div class="result-pick-line"><b>'+escape(totalPick)+'</b>'+grade(item.total_result)+'</div></div>'
      +'</div>'
      +(fallback?'<div class="result-game-note">† Retrospective direction from the archived Baseline forecast; not an original Injury pick.</div>':'')
      +(rookie?'<div class="result-game-note">QB value uncalibrated · research-only prediction</div>':'')
      +'</article>';
  }

  function render(data) {
    const raw=data.resultsGames||[],sourceSummary=data.resultsSummary||[];
    const games=data.directionalGames||[],summary=data.directionalSummary||[];
    const overall=verify(raw,sourceSummary,games,summary);
    const weeks=weeklyRows(games,summary);
    $('results-cards').innerHTML=resultCard(overall,'ats')+resultCard(overall,'totals');
    if(state.week===null)state.week=String(weeks[0]);
    if(state.week!=='all'&&!weeks.map(String).includes(state.week))state.week=String(weeks[0]);

    const weekSelect=$('results-week-filter'),daySelect=$('results-day-filter');
    const values=['<option value="all">All weeks</option>',...weeks.map(w=>
      '<option value="'+w+'">Week '+w+'</option>')].join('');
    if(weekSelect.innerHTML!==values)weekSelect.innerHTML=values;
    weekSelect.value=state.week;
    daySelect.value=state.day;

    if(!weekSelect.dataset.bound){
      weekSelect.addEventListener('change',()=>{state.week=weekSelect.value;render(data);});
      weekSelect.dataset.bound='yes';
    }
    if(!daySelect.dataset.bound){
      daySelect.addEventListener('change',()=>{state.day=daySelect.value;render(data);});
      daySelect.dataset.bound='yes';
    }

    const kickoffByGame=new Map((data.resultsKickoffs||[]).map(r=>[r.game_id,r.kickoff_utc]));
    const dayOrder={Thursday:0,Friday:1,Saturday:2,Sunday:3,Monday:4,Tuesday:5,Wednesday:6};
    function chronological(a,b){
      const aTime=Date.parse(a.kickoff_utc||kickoffByGame.get(a.game_id)||'');
      const bTime=Date.parse(b.kickoff_utc||kickoffByGame.get(b.game_id)||'');
      if(Number.isFinite(aTime)&&Number.isFinite(bTime))return aTime-bTime||a.game_id.localeCompare(b.game_id);
      return (dayOrder[a.day]??7)-(dayOrder[b.day]??7)||a.game_id.localeCompare(b.game_id);
    }
    const filtered=games.filter(g=>(state.week==='all'||String(g.week)===state.week)
      &&(state.day==='all'||g.day===state.day))
      .sort((a,b)=>Number(b.week)-Number(a.week)
        ||chronological(a,b));
    const complete=filtered.filter(g=>g.score_status==='FINAL').length;
    $('results-game-desc').textContent=filtered.length+' games · '+complete+' final'
      +(filtered.length-complete?' · '+(filtered.length-complete)+' pending':'');
    $('results-details').innerHTML=filtered.length
      ?filtered.map(gameCard).join('')
      :'<div class="results-empty">No games match those filters.</div>';
  }

  window.renderPublicResults=render;
})();
