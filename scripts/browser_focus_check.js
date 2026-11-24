async page => {
    const base='http://127.0.0.1:5059';
    if(!page.url().startsWith(base))throw new Error('Disposable fixture only.');
    await page.evaluate(() => localStorage.removeItem('quiz-focus-results'));
    const adminContext=await page.context().browser().newContext({viewport:{width:820,height:700}});
    await adminContext.request.post(base+'/login',{form:{username:'admin1',password:'test-password'}});
    await adminContext.request.post(base+'/admin/round/activate/1');
    const admin=await adminContext.newPage();
    await admin.goto(base+'/admin/round-control');
    await admin.locator('button').filter({hasText:'STOP'}).focus();
    await admin.evaluate(()=> {window.__focused=document.activeElement;document.documentElement.style.scrollBehavior='auto';window.scrollTo({top:300,behavior:'instant'});});
    await admin.waitForFunction(()=>window.scrollY===300);
    const scroll=await admin.evaluate(()=>window.scrollY);
    const answered=Number((await admin.locator('[data-flip-key="1"] .progress-bar').textContent()).trim().split('/')[0]);
    await page.context().request.post(base+'/tabulator/scoring/1/save',{data:{question:answered+1,status:'correct'}});
    await new Promise(r=>setTimeout(r,1300));
    const focus=await admin.evaluate(()=>window.__focused===document.activeElement && window.__focused.isConnected);
    if(!focus)throw new Error('Focus lost during live update');
    await admin.evaluate(()=>document.activeElement.blur());
    await admin.waitForFunction(n=>document.querySelector('[data-flip-key="1"]').textContent.includes(n+'/30'),answered+1,{timeout:2000});
    const finalScroll=await admin.evaluate(()=>window.scrollY);
    if(finalScroll!==scroll)throw new Error(`Scroll changed: ${scroll} => ${finalScroll}`);
    await page.evaluate(value=>localStorage.setItem('quiz-focus-results',JSON.stringify(value)),{focus_preserved:true,scroll_preserved:true,scroll_y:scroll});
    await adminContext.close();
}
