/* Tedgy Trends read-only, continuously updated NFL prospective results UI.
   All grades are GitHub Actions outputs from frozen pregame forecasts and
   explicit FINAL NFL scores; never grade or train in the browser. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value === null || value === undefined ? '' : value)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  const num = value => value === '' || value === null || value === undefined ? NaN : Number(value);
  const expectedStatus = new Set(['FINAL','PENDING']);
  const grades = new Set(['Win','Loss','Push','No lean','Pending']);
  const stat = (rec,prefix,field) => {
    const value = num(rec[prefix + field]);
    return Number.isFinite(value) ? value : 0;
  };
  const rec = (row,market) => {
    if (!row) return '—';
    const pref = market === 'ats' ? 'ats_' : 'totals_';
    const w = stat(row,pref,'wins'), l=stat(row,pref,'losses'), p=stat(row,pref,'pushes');
    return w+'–'+l+(p ? '–'+p : '');
  };
  const roi = (row,market) => {
    if (!row) return '—';
    const key='illustrative_flat_110_'+(market==='ats'?'ats':'totals')+'_roi_pct';
    return Number.isFinite(num(row[key])) ? num(row[key]).toFixed(1)+'%' : '—';
  };
  const formatDate = value => {
    const t=new Date(value);
    return Number.isFinite(t.getTime()) ?
      new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',month:'short',
         day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(t)
      : 'Unverified';
  };
  const gradeLabel = value => {
    const s=String(value||'Pending');
    const color = s==='Win' ? '#b8e58d' : s==='Loss' ? '#ffb7b0' : '#c9d1db';
    return '<span style="font-weight:800;color:'+color+'">'+esc(s)+'</span>';
  };
  const summaryFor=(summary,week,model,klass)=>
      summary.find(s=>String(s.week)===String(week)&&s.model===model&&s.record_class===klass);
  const tally=(games,model,field)=>{
    const vals=games.filter(r=>r.model===model&&r.record_class==='PUBLIC_PUBLISHED'
       &&r.score_status==='FINAL');
    return {wins:vals.filter(r=>r[field]==='Win').length,
      losses:vals.filter(r=>r[field]==='Loss').length,
      pushes:vals.filter(r=>r[field]==='Push').length,
      no_lean:vals.filter(r=>r[field]==='No lean').length};
  };
  const validate=(games,summary)=>{
    if(!Array.isArray(games)||games.length<58)throw Error('Results source does not cover original Week8 and Week9 public records');
    if(!Array.isArray(summary)||summary.length<6)throw Error('Missing week-by-week results summary');
    const seen=new Set();
    for(const r of games){
      if(!r.game_id||!['baseline','injury'].includes(r.model)||!expectedStatus.has(r.score_status))
        throw Error('Invalid game/model/status in results archive');
      const key=r.game_id+'|'+r.model;
      if(seen.has(key))throw Error('Duplicate graded game/model row '+key);
      seen.add(key);
      if(!grades.has(r.ats_result)||!grades.has(r.total_result))
        throw Error('Nonstandard game result '+key);
      if(r.score_status==='PENDING' && (r.ats_result!=='Pending'||r.total_result!=='Pending'||String(r.actual_home).trim()!==''))
        throw Error('Pending game prematurely graded');
      if(r.score_status==='FINAL' && (![r.actual_home,r.actual_away].every(x=>Number.isInteger(num(x)))||
          !r.score_source_url))
        throw Error('FINAL game has no authenticated final score');
      if(String(r.week)==='9'&&r.model==='baseline'&&r.record_class!=='RESEARCH_COMPARATOR')
        throw Error('Week9 retrospective Baseline improperly promoted to official cumulative record');
    }
    const current=new Set(games.map(r=>String(r.week)));
    if(!current.has('8')||!current.has('9')||!current.has('10'))
      throw Error('Results are missing a known published week');
    for(const [wk,count] of [['8',14],['9',15],['10',14]]){
      const sub=games.filter(r=>String(r.week)===wk);
      if(sub.length!==count*2||new Set(sub.map(r=>r.game_id)).size!==count)
        throw Error('Incomplete Week '+wk+' result cohort: '+sub.length);
    }
    for(const model of ['baseline','injury']){
      const official=summaryFor(summary,'ALL',model,'PUBLIC_PUBLISHED');
      if(!official)throw Error('Missing cumulative '+model+' record');
      const included=games.filter(r=>r.model===model&&r.record_class==='PUBLIC_PUBLISHED');
      if(num(official.games_expected)!==included.length
         ||num(official.games_final)!==included.filter(r=>r.score_status==='FINAL').length)
         throw Error('Cumulative graded game count mismatch '+model);
      for(const [field,prefix] of [['ats_result','ats_'],['total_result','totals_']]){
        const t=tally(games,model,field);
        for(const [key,col] of [['wins','wins'],['losses','losses'],['pushes','pushes'],['no_lean','no_lean']]){
          if(t[key]!==num(official[prefix+col]))
            throw Error('Cumulative '+model+' '+field+' '+key+' disagrees with game-by-game grades');
        }
      }
    }
  };
  const filterState={week:'all',day:'all'};
  const shownWeek=(row)=>filterState.week==='all'||String(row.week)===filterState.week;
  const shownDay=(row)=>filterState.day==='all'||row.day===filterState.day;
  const finalText=(r)=>{
    if(!r||r.score_status!=='FINAL')return 'Pending';
    return esc(r.away_team)+' '+esc(r.actual_away)+' – '+esc(r.home_team)+' '+esc(r.actual_home);
  };
  function render(data){
    const games=data.resultsGames||[],summary=data.resultsSummary||[];
    validate(games,summary);
    const totalFinal=new Set(games.filter(r=>r.score_status==='FINAL').map(r=>r.game_id)).size;
    const totalPending=new Set(games.filter(r=>r.score_status==='PENDING').map(r=>r.game_id)).size;
    const latest=summary[0]?.last_grade_run_utc;
    $('results-notice').innerHTML='<span style="font-size:20px;color:var(--accent)">ⓘ</span>'
      +'<div><strong>2026 overall Injury model · '+totalFinal+' games final'
      +(totalPending?' · '+totalPending+' pending':'')+'.</strong> '
      +'Week 8 onward. Results update automatically after Thursday, Sunday and Monday games become FINAL. '
      +'Last graded '+esc(formatDate(latest))+'. Actual game totals are displayed even if the model had no pregame pick. '
      +'These are model projection records, not placed bets.</div>';

    const cards=['ats','totals'];
    $('results-cards').innerHTML=cards.map(market=>{
      const result=summaryFor(summary,'ALL','injury','PUBLIC_PUBLISHED');
      if(!result)throw Error('Official cumulative Injury record missing');
      const c=rec(result,market),win=market==='ats'?result.ats_win_pct:result.totals_win_pct;
      const finished=num(result.games_final),pending=num(result.games_pending);
      const neutral=market==='ats'?num(result.ats_no_lean):num(result.totals_no_lean);
      const pushed=market==='ats'?num(result.ats_pushes):num(result.totals_pushes);
      const graded=finished-neutral;
      const numWin=Number.isFinite(num(win))?num(win).toFixed(1)+'%':'—';
      return '<div class="model-card"><div class="model-name">OVERALL INJURY MODEL · '
        +(market==='ats'?'ATS RECORD':'TOTALS RECORD')+'</div>'
        +'<div class="model-value">'+esc(c)+'</div>'
        +'<div class="model-desc">'+graded+' directional results'
        +(pushed?' · '+pushed+' push':'')
        +' · '+numWin+' win rate · '+roi(result,market)+' illustrative -110 ROI'
        +(neutral?' · '+neutral+' game with no pregame pick':'')
        +(pending?' · '+pending+' pending':'')+'</div></div>';
    }).join('');

    const weeks=[...new Set(games.map(r=>Number(r.week)))].sort((a,b)=>b-a);
    const weekFilter=$('results-week-filter'),dayFilter=$('results-day-filter');
    if(weekFilter){
      const choices=['<option value="all">All published weeks</option>'].concat(
        weeks.map(w=>'<option value="'+w+'">Week '+w+'</option>')
      ).join('');
      if(weekFilter.innerHTML!==choices)weekFilter.innerHTML=choices;
      if(!weeks.map(String).includes(filterState.week))filterState.week='all';
      weekFilter.value=filterState.week;
      if(!weekFilter.dataset.wired){
        weekFilter.addEventListener('change',()=>{
          filterState.week=weekFilter.value; render(data);
        });weekFilter.dataset.wired='true';
      }
    }
    if(dayFilter && !dayFilter.dataset.wired){
      dayFilter.addEventListener('change',()=>{
        filterState.day=dayFilter.value;render(data);
      });dayFilter.dataset.wired='true';
    }
    if(dayFilter)dayFilter.value=filterState.day;
    const weekRows=weeks.filter(w=>filterState.week==='all'||String(w)===filterState.week);
    const results=weekRows.map(w=>{
      const i=summaryFor(summary,w,'injury','PUBLIC_PUBLISHED');
      if(!i)throw Error('Missing Injury results row for Week '+w);
      const neutral=num(i.totals_no_lean),notes=neutral?' <small>('+neutral+' market-exact projection)</small>':'';
      return '<tr><td><b>Week '+w+'</b></td><td>'+esc(rec(i,'ats'))+'</td>'
      +'<td>'+esc(rec(i,'totals'))+notes+'</td><td>'+num(i.games_final)+'/'+num(i.games_expected)+'</td>'
      +'<td>'+roi(i,'ats')+'</td><td>'+roi(i,'totals')+'</td></tr>';
    });
    $('week-results').innerHTML=results.join('');
    $('week-title').textContent='Weekly Injury model record · 2026';
    $('results-desc').textContent='All published Injury-model directions are graded against archived pre-kickoff Bovada lines. '
      +'Actual final scores and market outcomes are shown for every completed matchup. '
      +'When the model projected exactly the bookmaker total, it made no pick; no win was invented. '
      +'ROI is a theoretical flat -110 benchmark, not actual betting returns.';

    const combined=new Map();
    for(const r of games.filter(g=>g.model==='injury'&&shownWeek(g)&&shownDay(g))){
      const key=r.game_id;
      if(combined.has(key))throw Error('Duplicate published Injury game '+key);
      combined.set(key,{game_id:r.game_id,week:Number(r.week),day:r.day,
        away:r.away_team,home:r.home_team,kickoff:r.kickoff_utc,injury:r});
    }
    const together=[...combined.values()].sort((a,b)=>b.week-a.week
      ||(b.kickoff||'').localeCompare(a.kickoff||'')||a.game_id.localeCompare(b.game_id));
    $('results-details').innerHTML=together.map(g=>{
      const pick=g.injury;
      const market=Number.isFinite(num(pick?.home_favored_spread))?
        (num(pick.home_favored_spread)>0?g.home+' -'+Math.abs(num(pick.home_favored_spread)):
         num(pick.home_favored_spread)<0?g.away+' -'+Math.abs(num(pick.home_favored_spread)):"PK")+
        ' / '+Number(pick.bovada_total).toFixed(1):'Unavailable';
      const gamemark=g.injury&&g.injury.source_warning.includes('NOT CALIBRATED')?
        ' <span title="First-start QB adjustment uncalibrated; not an official bet recommendation">†</span>':'';
      const finalTotal=pick.score_status==='FINAL'
        ?num(pick.actual_away)+num(pick.actual_home):NaN;
      const marketTotal=num(pick.bovada_total);
      const actualTotalResult=!Number.isFinite(finalTotal)?'Pending'
        :Math.abs(finalTotal-marketTotal)<1e-8?'Push'
        :finalTotal>marketTotal?'Over':'Under';
      const ats=pick.ats_pick==='No lean'?'No ATS pick':pick.ats_pick;
      const totalNeutral=pick.total_result==='No lean';
      const totalCell=totalNeutral
        ?'<span title="This model forecast matched the Bovada total exactly. It did not select a side.">No pregame pick</span>'
          +(pick.score_status==='FINAL'?' · Market '+gradeLabel(actualTotalResult)+' won':'')
        :esc(pick.total_pick)+' · '+gradeLabel(pick.total_result);
      return '<tr><td><b>W'+g.week+'</b> '+esc(g.day)+'</td>'
        +'<td>'+esc(g.away)+' @ '+esc(g.home)+gamemark+'</td>'
        +'<td>'+finalText(pick)+'</td><td>'+esc(market)+'</td>'
        +'<td>'+esc(ats)+' · '+gradeLabel(pick.ats_result)+'</td>'
        +'<td>'+totalCell+'</td>'
        +'<td>'+esc(Number.isFinite(finalTotal)?finalTotal+' total · '+actualTotalResult:actualTotalResult)+'</td></tr>';
    }).join('');
    $('results-game-desc').textContent=together.length+' games shown, '
      +together.filter(g=>g.injury?.score_status==='FINAL').length+' final; '
      +together.filter(g=>g.injury?.score_status==='PENDING').length+' awaiting final. '
      +'IND @ JAX Week 8 had a 46.0 model total versus Bovada 46.0: actual 49, so market Over won, but no pregame total pick was made. '
      +'† Miami QB adjustment uncalibrated. Select a week or day to filter.';
  }
  window.renderPublicResults=render;
})();
