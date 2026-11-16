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
    const nl=stat(row,pref,'no_lean');
    return w+'–'+l+(p ? '–'+p : '')+(nl?' · '+nl+' no lean':'');
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
      +'<div><strong>'+totalFinal+' NFL games graded · '+totalPending+' pending.</strong> '
      +'Auto-updated after Thursday, Sunday, and Monday game days, only after the scoreboard marks a game FINAL. '
      +'Last refreshed '+esc(formatDate(latest))+'. Week9 Baseline is a separately labeled research comparison; '
      +'Week10 injury QB uncertainty is retained. Graded directional leans are not placed bets.</div>';

    const cards=[['baseline','ats'],['injury','ats'],['baseline','totals'],['injury','totals']];
    $('results-cards').innerHTML=cards.map(([model,market])=>{
      const s=summaryFor(summary,'ALL',model,'PUBLIC_PUBLISHED');
      const c=rec(s,market),win=s?(market==='ats'?s.ats_win_pct:s.totals_win_pct):'';
      const count=s?num(s.games_final):0,pending=s?num(s.games_pending):0;
      const numWin=Number.isFinite(num(win))?num(win).toFixed(1)+'%':'—';
      return '<div class="model-card"><div class="model-name">'+(model==='injury'?'INJURY':'BASELINE')+' / '
        +(market==='ats'?'ATS':'TOTALS')+'</div><div class="model-value">'+esc(c)+'</div>'
        +'<div class="model-desc">'+numWin+' decisive win rate · '+roi(s,market)
        +' illustrative -110 ROI · '+count+' finished'
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
      const b=summaryFor(summary,w,'baseline',w===9?'RESEARCH_COMPARATOR':'PUBLIC_PUBLISHED');
      const i=summaryFor(summary,w,'injury','PUBLIC_PUBLISHED');
      if(!b||!i)throw Error('Missing model results row for Week '+w);
      const dateMark=w===9?' <span style="font-size:10px;color:var(--muted)">*research baseline</span>':'';
      return '<tr><td><b>Week '+w+'</b>'+dateMark+'</td><td>'+esc(rec(b,'ats'))+'</td>'
      +'<td>'+esc(rec(i,'ats'))+'</td><td>'+esc(rec(b,'totals'))+'</td>'
      +'<td>'+esc(rec(i,'totals'))+'</td><td>'+num(i.games_final)+'/'+num(i.games_expected)+'</td>'
      +'<td>'+roi(i,'ats')+' ATS / '+roi(i,'totals')+' totals</td></tr>';
    });
    $('week-results').innerHTML=results.join('');
    $('week-title').textContent='2026 weekly ATS and totals · Weeks 8 onward';
    $('results-desc').textContent='Official published directional records use Bovada lines archived before kickoff. '
      +'Week 9 Baseline is retrospective research and excluded from cumulative Baseline cards. '
      +'ROI is an illustrative -110 flat-stake comparison, not verified realized returns.';

    const combined=new Map();
    for(const r of games.filter(g=>shownWeek(g)&&shownDay(g))){
      const key=r.game_id;
      if(!combined.has(key))combined.set(key,{game_id:r.game_id,week:Number(r.week),day:r.day,
        away:r.away_team,home:r.home_team,kickoff:r.kickoff_utc,baseline:null,injury:null});
      const obj=combined.get(key);
      if(obj[r.model])throw Error('Duplicate game model in view');
      obj[r.model]=r;
    }
    const together=[...combined.values()].sort((a,b)=>b.week-a.week
      ||(b.kickoff||'').localeCompare(a.kickoff||'')||a.game_id.localeCompare(b.game_id));
    $('results-details').innerHTML=together.map(g=>{
      const pick=g.injury||g.baseline;
      const market=Number.isFinite(num(pick?.home_favored_spread))?
        (num(pick.home_favored_spread)>0?g.home+' -'+Math.abs(num(pick.home_favored_spread)):
         num(pick.home_favored_spread)<0?g.away+' -'+Math.abs(num(pick.home_favored_spread)):"PK")+
        ' / '+Number(pick.bovada_total).toFixed(1):'Unavailable';
      const gamemark=g.injury&&g.injury.source_warning.includes('NOT CALIBRATED')?
        ' <span title="First-start QB adjustment uncalibrated; not an official bet recommendation">†</span>':'';
      const result=model=>{
        const r=g[model];
        if(!r)return 'No saved projection';
        const research=r.record_class==='RESEARCH_COMPARATOR'?' <small>*research</small>':'';
        return gradeLabel(r.ats_result)+' / '+gradeLabel(r.total_result)+research;
      };
      return '<tr><td><b>W'+g.week+'</b> '+esc(g.day)+'</td>'
        +'<td>'+esc(g.away)+' @ '+esc(g.home)+gamemark+'</td>'
        +'<td>'+finalText(pick)+'</td><td>'+esc(market)+'</td>'
        +'<td>'+result('baseline')+'</td><td>'+result('injury')+'</td></tr>';
    }).join('');
    $('results-game-desc').textContent=together.length+' games shown, '
      +together.filter(g=>g.injury?.score_status==='FINAL').length+' final; '
      +together.filter(g=>g.injury?.score_status==='PENDING').length+' awaiting verified final. '
      +'† Miami QB EPA based on a first-time starter: research-only betting lean. '
      +'Choose a week or game day to filter; history stays visible.';
  }
  window.renderPublicResults=render;
})();
