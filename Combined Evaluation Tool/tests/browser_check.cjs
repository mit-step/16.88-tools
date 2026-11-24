// Optional: npm install --no-save playwright; npx playwright install chromium
const playwright=require('playwright');
const fs=require('fs');
(async()=>{
  const browser=await playwright.chromium.launch({headless:true,channel:process.env.REVIEW_BROWSER_CHANNEL||undefined});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`);});
    await page.goto(process.env.REVIEW_TEST_URL||'http://127.0.0.1:8080');
    const pdr=page.frameLocator('#panel-pdr iframe');
    await pdr.locator('#content .project-card').first().waitFor();
    await pdr.getByRole('link',{name:'CATENA',exact:true}).click();
    await pdr.getByRole('button',{name:/Live feedback/}).click();
    await page.getByRole('tab',{name:/CDR/}).click();
    const cdr=page.frameLocator('#panel-cdr iframe');
    await cdr.getByRole('link',{name:'CATENA',exact:true}).click();
    await cdr.getByRole('button',{name:'CDR checklist'}).click();
    if(await cdr.locator('[data-assess]').count()!==10)throw Error('Missing CDR criteria');
    await page.getByRole('tab',{name:/ESDP/}).click();
    const esdp=page.frameLocator('#panel-esdp iframe');
    await esdp.locator('#config-note').filter({hasText:/Local inventory is ready|AI content review available/}).waitFor();
    await esdp.getByRole('button',{name:/Explore the rubric/}).click();
    if(await esdp.locator('#rubric-cards article').count()!==12)throw Error('Missing ESDP criteria');
    // Results and form inputs are retained because tab switching does not reload frames.
    await page.getByRole('tab',{name:/PDR/}).click();
    if(await pdr.locator('.tabs button.active').textContent().then(t=>!t.includes('Live feedback')))throw Error('PDR tab state lost');
    fs.mkdirSync('test-results',{recursive:true});
    await page.screenshot({path:'test-results/suite-desktop.png'});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'test-results/suite-mobile.png'});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Shell overflows mobile viewport');
    await page.getByRole('tab',{name:/CDR/}).focus();
    await page.keyboard.press('ArrowRight');
    if(await page.getByRole('tab',{name:/ESDP/}).getAttribute('aria-selected')!=='true')throw Error('Keyboard tabs failed');
    if(errors.length)throw Error(errors.join('\n'));
    console.log('Passed: all three tools, namespaced APIs, CDR checklist, ESDP rubric, preserved tab state, mobile shell, keyboard navigation; no browser errors.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
