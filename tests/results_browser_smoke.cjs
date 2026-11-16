/* Real Chromium mobile/desktop Results smoke test. Uses local project CSVs
   in place of public GitHub raw requests; never relies on user cookies.
   Verifies actual DOM, width, cached JS revision, filters and both page routes. */
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'..');
const SITE=path.join(ROOT,'docs');
const PORT=8765;
const BASE_URL='http://127.0.0.1:'+PORT;

async function main(){
  const child=spawn('python3',['-m','http.server',String(PORT),'--bind','127.0.0.1','--directory',SITE],{stdio:'ignore'});
  try{
    // Wait for the local static preview port rather than partially parsing
    // aborted HTTP responses while the server is still starting.
    const net=require('node:net');
    let ready=false;
    for(let i=0;i<35;i++){
      ready=await new Promise(resolve=>{
        const socket=net.connect({host:'127.0.0.1',port:PORT});
        socket.once('connect',()=>{socket.destroy();resolve(true)});
        socket.once('error',()=>{socket.destroy();resolve(false)});
        socket.setTimeout(750,()=>{socket.destroy();resolve(false)});
      });
      if(ready)break;
      await new Promise(resolve=>setTimeout(resolve,250));
    }
    assert.ok(ready,'Local GitHub Pages preview server failed');
    const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    try{
      for(const viewport of [{width:390,height:844,name:'iphone'},{width:1365,height:900,name:'desktop'}]){
        for(const routeName of ['','week10.html']){
          const page=await browser.newPage({viewport:{width:viewport.width,height:viewport.height},deviceScaleFactor:1});
          const errors=[];
          page.on('pageerror',e=>errors.push(String(e)));
          await page.route('https://raw.githubusercontent.com/tedgytrends-bit/sports-betting-model/main/**',async route=>{
            const requestURL=new URL(route.request().url());
            const pos=requestURL.pathname.indexOf('/main/');
            if(pos<0){await route.abort();return}
            const relative=decodeURIComponent(requestURL.pathname.slice(pos+6));
            const abs=path.resolve(ROOT,relative);
            if(!abs.startsWith(ROOT+path.sep)||!fs.existsSync(abs)){await route.fulfill({status:404,body:'not found'});return}
            await route.fulfill({status:200,contentType:'text/csv; charset=utf-8',body:fs.readFileSync(abs)});
          });
          const target=BASE_URL+'/'+routeName+'?view=results';
          await page.goto(target,{waitUntil:'domcontentloaded'});
          await page.locator('.result-game-card').first().waitFor({timeout:30000});
          assert.equal(await page.locator('.result-overview-card').count(),2,'Must show two overall record cards');
          assert.equal(await page.locator('.result-game-card').count(),14,'Initial filter should show current Week10 games');
          assert.ok((await page.locator('#results-cards').innerText()).includes('24–18'),'Directional Injury total record missing');
          assert.ok((await page.locator('#results-cards').innerText()).includes('16–25–1'),'Injury ATS record missing');
          assert.equal(await page.locator('#results-error').isVisible(),false,'Error notice shown despite complete data');
          assert.equal(await page.locator('#view-results').evaluate(el=>el.classList.contains('active')),true);
          const metrics=await page.evaluate(()=>({
            width:window.innerWidth,
            documentWidth:document.documentElement.scrollWidth,
            bodyWidth:document.body.scrollWidth,
            cards:[...document.querySelectorAll('.result-overview-card')].map(x=>({
              width:Math.round(x.getBoundingClientRect().width),
              value:x.querySelector('.result-overview-value')?.innerText,
            })),
          }));
          assert.ok(metrics.documentWidth<=metrics.width+2,
            'Horizontal viewport overflow on '+viewport.name+': '+JSON.stringify(metrics));
          await page.selectOption('#results-week-filter','8');
          assert.equal(await page.locator('.result-game-card').count(),14,'Week8 should list all original games');
          const indi=page.locator('.result-game-card').filter({hasText:'IND @ JAX'});
          assert.equal(await indi.count(),1);
          assert.match(await indi.innerText(),/Over 46/i);
          assert.match(await indi.innerText(),/Win/i);
          assert.match(await indi.innerText(),/Retrospective/i);
          await page.selectOption('#results-week-filter','9');
          assert.equal(await page.locator('.result-game-card').count(),15);
          await page.selectOption('#results-week-filter','all');
          assert.equal(await page.locator('.result-game-card').count(),43);
          await page.selectOption('#results-day-filter','Monday');
          assert.ok(await page.locator('.result-game-card').count()>=1,'Monday games filter empty');
          assert.deepEqual(errors,[],'JavaScript page exceptions: '+errors.join('; '));
          // Full-site audit: remove old Week9 navigation and test every active view.
          const nav=viewport.width<850?'.mobile-nav':'.desktop-nav';
          const items=(await page.locator(nav).innerText()).toLowerCase();
          assert.ok(items.includes('projections')&&items.includes('results')&&items.includes('about'),
            'Navigation missing a main destination: '+items);
          assert.ok(!items.includes('week 9'),'Week9 archive must not have a top-level tab');
          await page.locator(nav+' [data-view="board"]').click();
          await page.locator('.game-card').first().waitFor({timeout:15000});
          assert.equal(await page.locator('.game-card').count(),14,'Full Week10 slate not loaded');
          assert.match(await page.locator('#kpi-games').innerText(),/14/);
          assert.match(await page.locator('.hero h1').first().innerText(),/Week 10 projections/);
          assert.match(await page.locator('#board-snapshot-label').innerText(),/Latest saved pregame/);
          assert.ok(await page.locator('.completed-strip').count()>=13,'Archived finals missing from the projection board');
          assert.ok(await page.locator('.game-injuries').count()>=10,'Official injury information unexpectedly missing');
          assert.equal(await page.locator('.game-injuries[open]').count(),0,
            'Detailed injury lists should be collapsed by default');
          const archives=page.locator('.past-boards');
          assert.equal(await archives.count(),1,'Past weekly boards must remain findable');
          await archives.locator('summary').click();
          assert.match(await archives.innerText(),/Week 9 projection archive/);
          assert.ok((await archives.locator('a[href="./week09.html"]').count())===1);
          await page.locator('#search').fill('Miami');
          assert.equal(await page.locator('.game-card').count(),1,'Team search failed');
          await page.locator('#search').fill('');
          assert.equal(await page.locator('.game-card').count(),14);
          await page.locator('[data-model="baseline"]').click();
          assert.equal(await page.locator('.game-card').count(),14);
          await page.locator('[data-model="injury"]').click();
          await page.locator('.game-card').first().locator('[data-game]').click();
          assert.ok(await page.locator('#overlay').evaluate(el=>el.classList.contains('open')),
            'Matchup detail drawer did not open');
          await page.locator('#close-drawer').click();
          assert.ok(!await page.locator('#overlay').evaluate(el=>el.classList.contains('open')));
          const boardWidth=await page.evaluate(()=>document.documentElement.scrollWidth);
          assert.ok(boardWidth<=viewport.width+2,'Projections horizontally overflow '+viewport.name+
            ': '+boardWidth+' versus '+viewport.width);
          await page.locator(nav+' [data-view="method"]').click();
          assert.match(await page.locator('#view-method h1').innerText(),/About the models/);
          assert.equal(await page.locator('#view-method .method-card').count(),4);
          assert.equal(await page.locator('.about-more[open]').count(),0);
          await page.locator('.about-more summary').click();
          assert.ok(await page.locator('.about-more a').count()>=5,'Audit sources are inaccessible');
          await page.locator(nav+' [data-view="results"]').click();
          assert.ok(page.url().includes('view=results'),'Deep link not updated when selecting Results');
          assert.equal(await page.locator('.result-overview-card').count(),2);
          fs.mkdirSync(path.join(ROOT,'artifacts'),{recursive:true});
          await page.selectOption('#results-week-filter','10');
          await page.selectOption('#results-day-filter','all');
          const screenshot='artifacts/results-'+viewport.name+(routeName?'-week10':'')+'.png';
          await page.screenshot({path:path.join(ROOT,screenshot),fullPage:false});
          console.log('PASS browser '+viewport.name+' '+(routeName||'index.html')+' cards='+metrics.cards.map(x=>x.value).join('/')+' viewport='+metrics.width+' docwidth='+metrics.documentWidth+' screenshot='+screenshot);
          if(!routeName){
            // Simulate an independently published future week. This is a
            // fixture ONLY, never a real forecast or user-facing Week11 pick.
            const future=await page.evaluate(()=>{
              const base=data.resultsGames.filter(r=>r.game_id==='2026_10_MIA_IND'&&
                r.record_class==='PUBLIC_PUBLISHED');
              if(base.length!==2)throw Error('Missing Week10 test model pair');
              const replacement=base.map(r=>({
                ...r,week:'11',game_id:'2026_11_MIA_IND',
                kickoff_utc:'2026-11-20T01:15:00+00:00',
                published_at_utc:'2026-11-18T15:00:00+00:00',
                quote_at_utc:'2026-11-18T14:00:00+00:00',
              }));
              data.resultsGames.push(...replacement);
              const week=buildPublishedWeek(11);
              data.games=week;
              showPublishedWeek(11);
              attachResultsToBoard();
              renderBoard();
              showView('board');
              return {game:week[0].id,week:publishedWeekNumbers()[0]};
            });
            assert.equal(future.game,'2026_11_MIA_IND');
            assert.equal(future.week,11);
            assert.equal(await page.locator('.game-card').count(),1);
            assert.match(await page.locator('#view-board .hero h1').innerText(),/Week 11 projections/);
            assert.match(await page.locator('#future-board-archives').innerText(),/Week 10 projection archive/);
            await page.locator('.game-card [data-game]').click();
            assert.match(await page.locator('#drawer-content').innerText(),/Both published models/i);
            await page.locator('#close-drawer').click();
            console.log('PASS synthetic future-week behavior: validated two model snapshots, archived Bovada, dynamic Week11 main board, Week10 preservation and matchup details');
          }
          await page.close();
        }
        // Historical board remains functional but has no competing stale
        // Results or Methodology tabs: those return to the current site.
        const archive=await browser.newPage({viewport:{width:viewport.width,height:viewport.height}});
        const archiveErrors=[];
        archive.on('pageerror',error=>archiveErrors.push(String(error)));
        await archive.route('https://raw.githubusercontent.com/tedgytrends-bit/sports-betting-model/main/**',async route=>{
          const parsed=new URL(route.request().url());
          const relative=decodeURIComponent(parsed.pathname.split('/main/')[1]||'');
          const file=path.resolve(ROOT,relative);
          if(!relative||!file.startsWith(ROOT+path.sep)||!fs.existsSync(file))
            return route.fulfill({status:404,body:'Missing archived CSV'});
          return route.fulfill({status:200,contentType:'text/csv',body:fs.readFileSync(file)});
        });
        await archive.goto(BASE_URL+'/week09.html',{waitUntil:'domcontentloaded'});
        await archive.locator('.game-card').first().waitFor({timeout:30000});
        assert.equal(await archive.locator('.game-card').count(),15,'Week9 archive missing frozen matchups');
        assert.match(await archive.locator('#view-board h1').innerText(),/Week 9 archive/);
        const archiveNav=viewport.width<850?'.mobile-nav':'.desktop-nav';
        assert.equal(await archive.locator(archiveNav+' a[href="./"]').count(),1);
        assert.equal(await archive.locator(archiveNav+' a[href="./?view=results"]').count(),1);
        assert.equal(await archive.locator(archiveNav+' a[href="./?view=method"]').count(),1);
        assert.equal(await archive.locator(archiveNav+' [data-view="results"]').count(),0,
          'Do not show stale Week8 Results on the historical archive');
        const archiveWidth=await archive.evaluate(()=>document.documentElement.scrollWidth);
        assert.ok(archiveWidth<=viewport.width+2,
          'Week9 archive horizontally overflows on '+viewport.name);
        assert.deepEqual(archiveErrors,[], 'Week9 archive script errors');
        await archive.locator(archiveNav+' a[href="./?view=method"]').click();
        await archive.locator('#view-method.active').waitFor({timeout:25000});
        assert.match(await archive.locator('#view-method h1').innerText(),/About the models/);
        assert.ok(archive.url().includes('view=method'),'Historical About link lost its direct-view parameter');
        console.log('PASS browser '+viewport.name+' Week9 archive: 15 frozen games, current-site About link and Results navigation valid');
        await archive.close();
      }
    }finally{await browser.close()}
  }finally{child.kill('SIGTERM')}
}
main().catch(e=>{console.error(e.stack||String(e));process.exitCode=1});
