async page => {
    const base='http://127.0.0.1:5059';
    if(!page.url().startsWith(base)) throw new Error('Disposable fixture only');
    await page.evaluate(() => localStorage.removeItem('quiz-pending-results'));
    const admin=await page.context().browser().newContext();
    await admin.request.post(base+'/login',{form:{username:'admin1',password:'test-password'}});
    await admin.request.post(base+'/admin/round/activate/1');
    await page.addInitScript(()=> { const add=window.addEventListener;window.__beforeUnload=[];window.addEventListener=function(type,fn,options){if(type==='beforeunload')window.__beforeUnload.push(fn);return add.call(this,type,fn,options);};});
    await page.goto(base+'/tabulator/scoring/1');
    await page.context().setOffline(true);
    await page.locator('label[for="q10_correct"]').click();
    await page.waitForFunction(()=>document.querySelector('#save-status').textContent.includes('Retrying'));
    await admin.request.post(base+'/admin/round/stop/1');
    await page.context().setOffline(false);
    await page.waitForFunction(()=>document.querySelector('#round-closed-msg').textContent.includes('1 answers remain unsaved'),{timeout:4000});
    await new Promise(r=>setTimeout(r,3500));
    if(!page.url().endsWith('/scoring/1')) throw new Error('Unsaved answer redirected away');
    await admin.request.post(base+'/admin/round/activate/1');
    const warned=await page.evaluate(()=> {
        const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);
        for(const fn of window.__beforeUnload || [])window.removeEventListener('beforeunload',fn);
        return event.defaultPrevented;
    });
    if(!warned)throw new Error('Closed round draft did not warn before navigation');
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#save-status').textContent.includes('All answers saved'));
    await page.reload();
    if(!await page.locator('#q10_correct').isChecked())throw new Error('Retained answer not persisted after reopening');
    await page.evaluate(()=>localStorage.setItem('quiz-pending-results',JSON.stringify({closed_round_retains_draft:true,reopening_commits_retained_answer:true})));
    await admin.close();
}
