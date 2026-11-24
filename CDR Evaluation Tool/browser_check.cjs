const {chromium}=require('C:/Users/never/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:"msedge"});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8766');
 await page.getByRole('heading',{name:'CDR evaluation workspace'}).waitFor();
 await page.screenshot({path:'workspace-preview.png',fullPage:true});
 await page.getByRole('link',{name:'CDR requirements'}).click();
 await page.getByRole('heading',{name:'Source differences and calendar'}).waitFor();
 await page.goto('http://127.0.0.1:8766/#catena');
 await page.getByRole('button',{name:'CDR checklist'}).click();
 await page.getByRole('heading',{name:'Final design',exact:true}).waitFor();
 if(await page.locator('[data-assess]').count()!==10)throw Error('Expected ten checklist criteria');
 await page.screenshot({path:'checklist-preview.png',fullPage:true});
 if(errors.length)throw Error(errors.join('\n'));
 console.log('Browser check passed: overview, requirements, all ten checklist criteria; no JavaScript errors.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

