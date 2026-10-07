const {chromium}=require(process.env.STUDIO_NODE_MODULES+'/playwright');
const {spawn,execFileSync}=require('child_process'),fs=require('fs'),os=require('os'),path=require('path');
(async()=>{
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'studio-ui-test-'));
let child,browser;
try{
 fs.mkdirSync(path.join(tmp,'productions'));
 child=spawn('python',['-B','_infra/creative-studio/server.py','--root',tmp,'--port','0'],{windowsHide:true});
 const base=await new Promise((resolve,reject)=>{let text='';child.stdout.on('data',b=>{text+=b;const m=text.match(/http:\/\/127\.0\.0\.1:\d+/);if(m)resolve(m[0]);});child.on('error',reject);child.on('exit',code=>reject(Error('server exit '+code)));});
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.getByText('새 이야기의 시작').waitFor();
 execFileSync('python',['-B','_infra/creative-studio/project_store.py','--root',tmp,'create','live-test','--title','자동 반영 시험']);
 await page.waitForFunction(()=>document.querySelector('#title').textContent==='자동 반영 시험',null,{timeout:12000});
 const p=path.join(tmp,'productions/video/live-test'),patch=path.join(tmp,'cut.json');
 fs.writeFileSync(patch,JSON.stringify({id:'01',name:'대화에서 나온 컷'}));
 execFileSync('python',['-B','_infra/creative-studio/project_store.py','upsert-cut',p,'--file',patch]);
 await page.getByRole('heading',{name:'대화에서 나온 컷'}).waitFor({timeout:12000});
 await page.locator('[data-open="01"]').first().click();await page.locator('#note').fill('아직 저장 안 한 메모');
 fs.writeFileSync(patch,JSON.stringify({id:'01',name:'업데이트된 컷'}));execFileSync('python',['-B','_infra/creative-studio/project_store.py','upsert-cut',p,'--file',patch]);
 await page.waitForTimeout(3600);
 if(await page.locator('#note').inputValue()!=='아직 저장 안 한 메모')throw Error('Unsaved note lost during polling');
 await page.locator('#save-note').click();await page.waitForFunction(()=>document.querySelector('#message').textContent==='저장했습니다.');await page.locator('#close').click();
 await page.getByRole('heading',{name:'업데이트된 컷'}).waitFor();
 await page.reload();await page.locator('[data-open="01"]').first().click();if(await page.locator('#note').inputValue()!=='아직 저장 안 한 메모')throw Error('Note failed to persist');
 if(errors.length)throw Error(errors.join('\n'));
 console.log(JSON.stringify({newProjectAutoDetected:true,newCutAutoDetected:true,updatedCutAutoDetected:true,unsavedNotePreserved:true,savedNoteReloaded:true,jsErrors:0}));
}finally{
 if(browser)await browser.close();if(child){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill();if(child.exitCode===null)await exited;}
 const resolved=path.resolve(tmp),tempRoot=path.resolve(os.tmpdir());if(!resolved.startsWith(tempRoot+path.sep)||!path.basename(resolved).startsWith('studio-ui-test-'))throw Error('Unexpected test cleanup path');fs.rmSync(resolved,{recursive:true,force:true});
}
})().catch(e=>{console.error(e);process.exit(1)});
