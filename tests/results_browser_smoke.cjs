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
const URL='http://127.0.0.1:'+PORT;

async function main(){
  const child=spawn('python3',['-m','http.server',String(PORT),'--bind','127.0.0.1','--directory',SITE],{stdio:'ignore'});
  try{
    let ready=false;
    for(let i=0;i<35;i++){
      try{const resp=await fetch(URL+'/index.html');if(resp.ok){ready=true;break}}catch{}
      await new Promise(r=>setTimeout(r,250));
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
          const target=URL+'/'+routeName+'?view=results';
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
          fs.mkdirSync(path.join(ROOT,'artifacts'),{recursive:true});
          await page.selectOption('#results-week-filter','10');
          await page.selectOption('#results-day-filter','all');
          const screenshot='artifacts/results-'+viewport.name+(routeName?'-week10':'')+'.png';
          await page.screenshot({path:path.join(ROOT,screenshot),fullPage:false});
          console.log('PASS browser '+viewport.name+' '+(routeName||'index.html')+' cards='+metrics.cards.map(x=>x.value).join('/')+' viewport='+metrics.width+' docwidth='+metrics.documentWidth+' screenshot='+screenshot);
          await page.close();
        }
      }
    }finally{await browser.close()}
  }finally{child.kill('SIGTERM')}
}
main().catch(e=>{console.error(e.stack||String(e));process.exitCode=1});
