async (page) => {
    if (!page.url().startsWith('http://127.0.0.1:5059/')) throw new Error('Use the disposable serve_fixture.py server on port 5059.');
    const results = {}, errors = [], external = [];
    const base = 'http://127.0.0.1:5059';
    const assert = (condition, message) => { if (!condition) throw new Error(message); };
    const context = page.context();
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', d => d.accept());
    await context.route('**/*', route => {
        if (!route.request().url().startsWith(base)) { external.push(route.request().url()); return route.abort(); }
        return route.continue();
    });
    const setup=await context.browser().newContext();
    await setup.request.post(base+'/login',{form:{username:'admin1',password:'test-password'}});
    await setup.request.post(base+'/admin/round/activate/1');
    await setup.close();
    await context.request.post(base+'/login',{form:{username:'tab1',password:'test-password'}});
    for (const [question,status] of [[1,'correct'],[2,'wrong'],[3,'correct'],[4,'wrong']]) {
        await context.request.post(base+'/tabulator/scoring/1/save',{data:{question,status}});
    }
    await page.evaluate(() => localStorage.clear());
    await page.addInitScript(() => {
        const add=window.addEventListener;
        window.__beforeUnload=[];
        window.addEventListener=function(type,fn,options) {
            if(type==='beforeunload')window.__beforeUnload.push(fn);
            return add.call(this,type,fn,options);
        };
    });
    await page.goto(base + '/tabulator/scoring/1');
    await page.evaluate(() => document.fonts.ready);
    assert(await page.evaluate(() => document.fonts.check('400 16px Poppins')), 'Poppins did not load locally');
    assert(await page.locator('#q1_correct').isChecked(), 'Initial saved answer absent');
    await page.locator('.lock-btn[data-q="1"]').click();
    assert(await page.locator('#q1_correct').isDisabled(), 'Lock did not disable answers');
    await page.reload();
    assert(await page.locator('#q1_correct').isDisabled(), 'Lock lost on reload');
    await page.locator('.lock-btn[data-q="1"]').click();
    results.lock_survives_reload = true;
    await page.evaluate(() => {
        for (const status of ['wrong','correct','wrong','correct']) {
            const input=document.getElementById('q1_'+status); input.checked=true; input.dispatchEvent(new Event('change',{bubbles:true}));
        }
    });
    await page.waitForFunction(() => document.querySelector('#save-status').textContent.includes('All answers saved'));
    await page.reload();
    assert(await page.locator('#q1_correct').isChecked(), 'Rapid edits lost latest answer');
    results.rapid_edits = true;
    // Fail one save response and verify that the pending queue retries without losing the draft.
    let failNext=true;
    await page.route('**/scoring/1/save', route => {
        if (failNext) { failNext=false; return route.fulfill({status:503,contentType:'application/json',body:'{"error":"test retry"}'}); }
        return route.continue();
    });
    await page.locator('label[for="q2_correct"]').click();
    await page.waitForFunction(() => document.querySelector('#save-status').textContent.includes('Retrying'));
    await page.waitForFunction(() => document.querySelector('#save-status').textContent.includes('All answers saved'));
    results.retry_503 = true;
    await page.unroute('**/scoring/1/save');
    await context.setOffline(true);
    await page.locator('label[for="q3_wrong"]').click();
    await page.waitForFunction(() => document.querySelector('#save-status').textContent.includes('Retrying'));
    assert(await page.evaluate(() => Object.keys(localStorage).some(k=>k.startsWith('jpcs-draft') && localStorage.getItem(k).includes('wrong'))), 'Offline draft not retained');
    results.unsaved_navigation_warning=await page.evaluate(() => {
        const event=new Event('beforeunload',{cancelable:true}); window.dispatchEvent(event);
        for(const fn of window.__beforeUnload)window.removeEventListener('beforeunload',fn);
        return event.defaultPrevented;
    });
    assert(results.unsaved_navigation_warning, 'Pending saves do not warn before navigation');
    await context.setOffline(false);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#save-status').textContent.includes('All answers saved'));
    assert(await page.locator('#q3_wrong').isChecked(), 'Offline draft recovery failed');
    results.offline_reload_recovery = true;
    await page.setViewportSize({width:820,height:1180});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Tablet horizontal overflow');
    await page.screenshot({path:'output/playwright/scoring-tablet.png',fullPage:false,animations:'disabled'});
    const browser = context.browser();
    const adminContext=await browser.newContext({viewport:{width:1180,height:820}});
    const admin=await adminContext.newPage();
    await adminContext.request.post(base+'/login',{form:{username:'admin1',password:'test-password'}});
    await admin.goto(base+'/admin/round-control');
    const viewerContext=await browser.newContext({viewport:{width:1180,height:820}});
    const viewer=await viewerContext.newPage();
    let fragment200=0,fragment304=0,fullPolls=0;
    viewer.on('response', r=> { if(r.url().endsWith('/leaderboard/fragment')) { if(r.status()===304)fragment304++; if(r.status()===200)fragment200++; } });
    viewer.on('request', r=> { if(r.url()===base+'/leaderboard' && r.resourceType()==='fetch') fullPolls++; });
    await viewer.goto(base+'/leaderboard');
    const old=await viewer.locator('[data-flip-key="School 01"] .score-value').last().textContent();
    const start=Date.now();
    await page.locator('label[for="q4_correct"]').click();
    await viewer.waitForFunction(before => {
        const values=document.querySelectorAll('[data-flip-key="School 01"] .score-value');
        return values.length && Number(values[values.length-1].textContent) > Number(before);
    }, old, {timeout:2000});
    results.visible_update_ms=Date.now()-start;
    assert(results.visible_update_ms<=2000, 'Live update exceeded two seconds');
    await viewer.waitForResponse(r=>r.url().endsWith('/leaderboard/fragment') && r.status()===304,{timeout:4000});
    assert(fullPolls===0, 'Full page polling remains');
    results.fragment_responses={updated:fragment200,unchanged:fragment304,full_page_fetches:fullPolls};
    // Preserve admin modal while the network info refreshes.
    await admin.goto(base+'/admin/dashboard');
    await admin.getByRole('button',{name:'Connect Tabulators'}).click();
    await admin.waitForResponse(r=>r.url().endsWith('/admin/connection'));
    assert(await admin.locator('#connectModal').isVisible(), 'Open modal lost on refresh');
    results.modal_preserved = true;
    await admin.screenshot({path:'output/playwright/admin-connect.png',animations:'disabled'});
    // Simulated visibility suspension: hidden pages issue no polls and resume immediately.
    await viewer.evaluate(() => { window.__testHidden=true; Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.__testHidden}); document.dispatchEvent(new Event('visibilitychange')); });
    await new Promise(resolve=>setTimeout(resolve,1200));
    const previous=fragment200+fragment304;
    await new Promise(resolve=>setTimeout(resolve,1200));
    assert(fragment200+fragment304===previous,'Hidden page kept polling');
    await viewer.evaluate(() => { window.__testHidden=false; document.dispatchEvent(new Event('visibilitychange')); });
    await viewer.waitForResponse(r=>r.url().endsWith('/leaderboard/fragment'),{timeout:1500});
    results.simulated_hidden_resume = true;
    await adminContext.request.post(base+'/admin/round/stop/1');
    await page.waitForFunction(()=>!document.getElementById('round-closed').hidden,{timeout:2000});
    assert(await page.locator('#q1_correct').isDisabled(),'Stopped round still accepts UI input');
    await page.waitForURL('**/tabulator/dashboard');
    await adminContext.request.post(base+'/admin/round/activate/2');
    await page.getByRole('link',{name:'ENTER SCORING'}).waitFor({timeout:2000});
    assert(await page.getByRole('link',{name:'ENTER SCORING'}).getAttribute('href')==='/tabulator/scoring/2','Round transition wrong');
    results.stop_and_transition=true;
    await page.screenshot({path:'output/playwright/dashboard-tablet.png',animations:'disabled'});
    assert(external.length===0, 'External runtime assets: '+external.join(','));
    assert(errors.length===0,'Browser errors: '+errors.join(','));
    results.external_requests=external; results.browser_errors=errors;
    await adminContext.close(); await viewerContext.close();
    await page.evaluate(value => localStorage.setItem('quiz-verification-results',JSON.stringify(value)), results);
    console.log(JSON.stringify(results,null,2));
}
