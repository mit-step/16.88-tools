let state, currentTeam = null, currentTab = 'summary', currentPage = null, busy = false;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const initials = name => name.split(/[ :]+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();
const sourceUrl = (id, page) => `/files/${encodeURIComponent(id)}/document.pdf#page=${page}`;
const citation = source => `<a href="${sourceUrl(source.document, source.page)}" target="_blank" rel="noopener">${esc(source.filename)} · p. ${source.page} · ${esc(source.row)}</a>`;
const allPages = () => state.documents.flatMap(d => d.pages.map(p => ({...p, doc:d})));
const pending = () => allPages().filter(p => !p.verified);
function toast(message) { $('toast').textContent=message; $('toast').style.display='block'; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').style.display='none', 5000); }
async function load() {
  const response=await fetch('/api/workspace');
  if (!response.ok) throw new Error('Workspace is unavailable. Restart Start Workspace.cmd.');
  state=await response.json(); render();
}
async function post(path, payload) {
  const response=await fetch(path,{method:'POST', headers:{'Content-Type':'application/json','X-PDR-Token':state.csrf_token},body:JSON.stringify(payload)});
  const result=await response.json(); if(!response.ok) throw new Error(result.error || 'Could not save.'); return result;
}
function heading(eyebrow,title,description,right='') {return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="lede">${description}</p></div>${right}</div>`;}
function stats(items){return `<div class="stats">${items.map(([value,label])=>`<div class="stat"><strong>${value}</strong><span>${label}</span></div>`).join('')}</div>`;}
function render() {
  const route=decodeURIComponent(location.hash.slice(1));
  currentTeam=state.teams.find(t=>t.id===route) || null;
  const inbox=route==='inbox', requirements=route==='requirements';
  $('location').textContent=currentTeam?currentTeam.name:inbox?'Review inbox':requirements?'What’s next':'All projects';
  $('nav').innerHTML=`<a href="#" class="${!route?'active':''}">▦ <span>All projects</span></a><a href="#inbox" class="${inbox?'active':''}">◷ <span>Review inbox</span><span class="nav-count">${pending().length}</span></a><div class="nav-label">PROJECTS / TEAMS</div>${state.teams.map(t=>`<a href="#${t.id}" class="${currentTeam?.id===t.id?'active':''}"><span class="team-dot" style="background:${t.color}"></span>${esc(t.name)}</a>`).join('')}`;
  $('upload-team').innerHTML='<option value="">Detect from rubric or filename</option>'+state.teams.map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join('');
  $('upload-team').value=currentTeam?.id || '';
  $('use-ai').disabled=!state.ai_ready;
  $('ai-hint').textContent=state.ai_ready?'Sends uploaded page images to OpenAI; API charges may apply.':'Not configured. Native PDF reading and manual feedback entry work now.';
  if(!state.ai_ready)$('use-ai').checked=false;
  let output=requirements?renderRequirements():inbox?renderInbox():currentTeam?renderTeam():renderOverview();
  $('content').innerHTML=`<div class="page-wrap">${output}</div>`;
  document.querySelectorAll('[data-tab]').forEach(el=>el.addEventListener('click',()=>{currentTab=el.dataset.tab;render();}));
  document.querySelectorAll('[data-review]').forEach(el=>el.addEventListener('click',()=>openPage(el.dataset.doc,Number(el.dataset.review))));
  document.querySelectorAll('[data-print]').forEach(el=>el.addEventListener('click',()=>window.print()));
}
function renderOverview(){
  const pages=allPages(), read=pages.filter(p=>!['scan_pending','blank_page'].includes(p.method)).length;
  return heading('FROM PDR TO CDR','A clearer path to the next review.','Faculty feedback, organized by project. Explore each team’s draft priorities, trace comments to their source, and add new reviews as they arrive.',`<span class="cycle">${esc(state.cycle)}</span>`)+
    stats([[state.teams.length,'Projects / teams'],[state.documents.length,'Original review PDFs'],[read,'Pages with extracted text'],[pages.filter(p=>p.method==='scan_pending').length,'Scanned pages awaiting reading']])+
    `<div class="section-heading"><h2>Project feedback</h2><span>Draft summaries · ${state.teams.length} teams</span></div><div class="project-grid">${state.teams.map(t=>{
      const b=state.baselines[t.id], s=state.summaries[t.id];
      return `<a href="#${t.id}" class="project-card"><div class="card-top"><span class="monogram" style="background:${t.color}">${initials(t.name)}</span><div><div class="project-name">${esc(t.name)}</div><div class="card-caption">PDR → CDR · ${s.pages} source pages</div></div></div><p class="card-headline">${esc(b?.headline || 'Build the evidence for the next review.')}</p><ol class="card-priorities">${(b?.priorities||[]).map((p,i)=>`<li><span>0${i+1}</span>${esc(p.title)}</li>`).join('') || '<li>Add a rubric to start this team’s summary.</li>'}</ol><div class="card-bottom"><span>${s.comments} live feedback entries · ${s.pending_scans} scans pending</span><b>View feedback ↗</b></div></a>`;
    }).join('')}</div><div class="notice subtle">The priority previews above are imported from the pilot draft. Each team also has a live, source-linked summary that updates when readable reviews are uploaded. ${pending().length} pages still require instructor review.</div>`;
}
function renderTeam(){
  const t=currentTeam,s=state.summaries[t.id],b=state.baselines[t.id];
  const sourcePages=allPages().filter(p=>p.team===t.id);
  let output=heading('PROJECT FEEDBACK',esc(t.name),esc(b?.headline || 'Source-grounded feedback for the next review.'),'<button class="quiet no-print" data-print>Print / save PDF ↗</button>')+
    `<div class="tabs"><button data-tab="summary" class="${currentTab==='summary'?'active':''}">Summary</button><button data-tab="live" class="${currentTab==='live'?'active':''}">Live feedback · ${s.comments}</button><button data-tab="sources" class="${currentTab==='sources'?'active':''}">Sources & review · ${s.pages}</button></div>`;
  if(currentTab==='sources') return output+`<div class="section-heading"><h2>Original review pages</h2><span>${s.verified_pages} of ${s.pages} marked reviewed</span></div>`+renderSourceRows(sourcePages);
  if(currentTab==='live') return output+`<p class="lede">Extracted faculty comments grouped by rubric category. Exact repeated wording is grouped with all source locators; source counts do not represent independent reviewer votes.</p>${renderGroups(s)}`;
  output+=`<div class="summary-layout"><div><div class="panel"><span class="label">Live summary · updates with uploads</span><h2>What the source reviews say</h2><p class="hint">${s.read_pages} pages with readable or manually entered text; ${s.pending_scans} scans await transcription. Excerpts below preserve faculty wording. Expand a theme for all comments.</p>${renderGroups(s,true)}</div>`;
  if(b){
    output+=`<div class="panel"><span class="label amber">Pilot baseline · imported draft</span><h2>Strengths to retain</h2><p class="strengths">${esc(b.strengths)}</p><p class="reference"><a href="/reference/pilot.pdf#page=${b.page}" target="_blank" rel="noopener">${esc(b.source)} · p. ${b.page}</a> · ${esc(b.label)}</p></div><div class="panel"><span class="label amber">Pilot priorities for CDR</span><h2>Suggested next steps</h2><p class="hint">These priorities and deliverables are the pilot author’s synthesis. New uploads update the live summary above; this baseline stays as the historical reference.</p>${b.priorities.map((p,i)=>`<section class="priority"><h3><span class="priority-num">${i+1}.</span>${esc(p.title)}</h3><p><b>Faculty feedback as summarized in the pilot</b><br>${esc(p.faculty_feedback)}</p><div class="action"><b>Assistant-suggested deliverable</b>${esc(p.suggested_action)}</div></section>`).join('')}</div>`;
  }
  output+=`</div><aside class="summary-aside"><div class="panel"><span class="label">Evidence coverage</span><div class="meta-row"><span>Mapped source pages</span><b>${s.pages}</b></div><div class="meta-row"><span>Text / manual reading</span><b>${s.read_pages}</b></div><div class="meta-row"><span>Scans pending</span><b>${s.pending_scans}</b></div><div class="meta-row"><span>Instructor reviewed</span><b>${s.verified_pages}</b></div><p class="hint">Team mappings from the pilot are provisional. Reviewer coverage is not independently established.</p></div><div class="panel"><span class="label">Review discipline</span><p class="reference">Keep disagreements visible. A checked box does not cancel a narrative concern. Blank marks are not failures.</p><p class="reference">No automatic grades, consensus claims, or safety/readiness approvals are generated.</p></div></aside></div>`;
  return output;
}
function renderGroups(summary,compact=false){
  const groups=Object.entries(summary.groups).filter(([_,items])=>items.length);
  if(!groups.length) return '<div class="empty">No readable comments yet. Upload a text-based rubric or transcribe a scanned page in Sources & review.</div>';
  return groups.map(([cat,entries])=>{ const items=[...entries].reverse(); return `<details class="group" ${!compact?'open':''}><summary>${esc(cat)}<span>${items.length} ${items.length===1?'entry':'entries'}</span>${compact?`<p class="hint" style="font-weight:400;margin:8px 0 0;max-width:90%">${esc(items[0].text.length>180?items[0].text.slice(0,177)+'…':items[0].text)}</p>`:''}</summary>${items.map(item=>`<div class="evidence"><p>${esc(item.text)}</p>${item.sources.map(s=>`${citation(s)}<small>Literal marks — completeness: ${esc(s.complete)||'(blank)'}; quality: ${esc(s.quality)||'(blank)'} · ${s.verified?'instructor reviewed':'draft extraction'}${s.uncertainty?' · '+esc(s.uncertainty):''}</small>`).join('')}</div>`).join('')}</details>`; }).join('');
}
function renderSourceRows(pages){
  if(!pages.length)return '<div class="empty">No matching source pages.</div>';
  return `<div class="source-list">${pages.map(p=>`<div class="source-row"><div><strong>${esc(p.doc.filename)} · p. ${p.number}</strong><p>${esc(state.teams.find(t=>t.id===p.team)?.name||'Unassigned')} · ${esc(p.mapping_basis)}</p><p><span class="pill ${p.verified?'green':''}">${p.verified?'Instructor reviewed':p.method==='scan_pending'?'Scan awaiting transcription':'Draft · review needed'}</span> <span>${p.comments.filter(c=>c.text).length} comments</span></p></div><button class="quiet" data-doc="${p.doc.id}" data-review="${p.number}">Review page ↗</button></div>`).join('')}</div>`;
}
function renderInbox(){
  const pages=pending(),unassigned=pages.filter(p=>!p.team);
  return heading('EVIDENCE CHECK','Review inbox','Resolve uncertain identities, inspect extracted text, and add feedback from handwritten sheets. A page stays in this inbox until you confirm full-page review.')+
    stats([[pages.length,'Pages requiring review'],[unassigned.length,'Unassigned pages'],[pages.filter(p=>p.method==='scan_pending').length,'Scans awaiting transcription'],[allPages().filter(p=>p.verified).length,'Pages marked reviewed']])+
    (unassigned.length?`<div class="section-heading"><h2>Identity needs attention</h2><span>Never assigned by adjacency</span></div>${renderSourceRows(unassigned)}`:'')+
    `<div class="section-heading"><h2>Mapped pages awaiting review</h2><span>Review text and original image together</span></div>${renderSourceRows(pages.filter(p=>p.team))}`;
}
function renderRequirements(){
  return heading('BUILD IN STAGES','Useful now. Ready to grow.','The summary and evaluation workspace runs locally with the supplied documents. More advanced automation can be added without rebuilding the evidence foundation.')+
    `<div class="requirements-grid" style="margin-top:30px"><div class="panel"><span class="label">Available now</span><h2>Summary & evaluation workspace</h2><ul><li>Six team workspaces with imported pilot drafts and live feedback summaries.</li><li>PDF uploads, exact-file deduplication, and automatic team matching from known names.</li><li>Local extraction of readable rubric tables, with literal marks and source locators.</li><li>Team assignment, manual transcription, full-page review, and a review inbox.</li><li>Persistent local files, summary updates, data export, and workspace history.</li></ul></div><div class="panel"><span class="label amber">For full automation</span><h2>What still needs to be provided</h2><ul><li><b>AI reading:</b> a server-side API key and a vision-capable model to transcribe handwriting. Currently ${state.ai_ready?'configured':'not configured'}.</li><li><b>Verified identity:</b> a roster of team names/aliases and reviewer spellings. New teams currently require a configuration edit.</li><li><b>Grading, if desired:</b> explicit scoring rules, weights, and instructor-graded examples. No grades are inferred from these forms.</li><li><b>Quality validation:</b> instructor-adjudicated examples and acceptable error thresholds.</li><li><b>Shared deployment:</b> an AWS server is available per the supplied server README. Choose a subdomain, access/Touchstone requirements, storage policy, and who may approve feedback. No deployment has been performed.</li></ul></div></div><div class="notice subtle">For automatic updates today, upload a text-readable PDF with an identifiable team name or select the team. Handwritten scans can be stored immediately and added to the summary after manual transcription, or read through the optional configured AI service.</div><div class="panel"><h2>How this prototype summarizes</h2><p class="muted">The live summary groups extracted faculty comments by rubric category and collapses exact repeated wording while preserving every source citation. It does not infer reviewer agreement or silently rewrite historical priorities. The richer priority narrative from the original pilot is retained as a labeled baseline.</p><p class="muted">Instructor review is required to confirm semantic fidelity, safety coverage, and conflicting advice. The earlier command-line tool remains available for optional AI-generated priority drafts and structural audits.</p></div>`;
}
function openPage(docId,number){
  currentPage={docId,number};
  const doc=state.documents.find(d=>d.id===docId),p=doc.pages[number-1];
  $('page-title').textContent=`${doc.filename} · p. ${number}`;
  $('page-content').innerHTML=`<div class="page-review-grid"><div><a href="${sourceUrl(docId,number)}" target="_blank" rel="noopener"><img class="page-image" src="/files/${docId}/page-${number}.png" alt="Original review page ${number}"></a><p class="hint">Click image to open original PDF.</p></div><div class="page-controls"><div class="notice">${esc(p.limitations)}</div><label class="field">Project / team<select id="page-team"><option value="">Unassigned / quarantine</option>${state.teams.map(t=>`<option value="${t.id}" ${p.team===t.id?'selected':''}>${esc(t.name)}</option>`).join('')}</select></label><button class="quiet" id="assign-page">Save team assignment</button><h3>Extracted feedback</h3>${p.comments.filter(c=>c.text).map(c=>`<div class="evidence"><span class="label">${esc(c.category)}</span><p>${esc(c.text)}</p><small>Completeness: ${esc(c.complete)||'(blank)'} · quality: ${esc(c.quality)||'(blank)'}</small></div>`).join('') || '<p class="hint">No comments transcribed yet.</p>'}<h3>Add a transcribed comment</h3><p class="hint">Enter faculty feedback as written. Preserve uncertain words and questions; do not add your suggested action here.</p><label class="field">Rubric category<select id="note-category">${state.categories.map(c=>`<option>${esc(c)}</option>`).join('')}</select></label><label class="field">Faculty comment<textarea id="note-text" placeholder="Transcribe a comment from this page…"></textarea></label><button class="quiet" id="save-note">Add comment to summary</button><hr style="border:0;border-top:1px solid var(--border);margin-top:24px"><label class="check"><input type="checkbox" id="confirm-page"><span>I checked all comments, marks, handwriting and team identity against the full original page. Unknown identity remains quarantined.</span></label><button class="primary" id="verify-page">Mark full page reviewed</button><p id="page-result" role="status"></p></div></div>`;
  if(!$('page-dialog').open)$('page-dialog').showModal();
  const mutate=async payload=>{
    try{
      const result=await post('/api/page',{document:docId,page:number,...payload});
      await load(); openPage(docId,number); toast(result.message);
    }catch(error){$('page-result').textContent=error.message;$('page-result').className='error';}
  };
  $('assign-page').onclick=()=>mutate({action:'assign',team:$('page-team').value});
  $('save-note').onclick=()=>mutate({action:'note',category:$('note-category').value,text:$('note-text').value});
  $('verify-page').onclick=()=>mutate({action:'verify',confirmed:$('confirm-page').checked});
}
function setFiles(files){
  const transfer=new DataTransfer(); [...files].forEach(f=>transfer.items.add(f)); $('files').files=transfer.files;
  $('file-list').innerHTML=[...files].map(f=>`<div class="file-item">${esc(f.name)} · ${(f.size/1024/1024).toFixed(1)} MB</div>`).join('');
}
$('open-upload').onclick=()=>{$('upload-result').textContent='';$('upload-team').value=currentTeam?.id||'';$('upload-dialog').showModal();};
document.querySelectorAll('.close-dialog').forEach(el=>el.onclick=()=>{if(!busy)$('upload-dialog').close();});
$('close-page').onclick=()=>$('page-dialog').close();
$('files').onchange=()=>setFiles($('files').files);
$('drop-zone').ondragover=e=>{e.preventDefault();$('drop-zone').classList.add('drag');};
$('drop-zone').ondragleave=()=>$('drop-zone').classList.remove('drag');
$('drop-zone').ondrop=e=>{e.preventDefault();$('drop-zone').classList.remove('drag');setFiles(e.dataTransfer.files);};
$('upload-form').onsubmit=async e=>{
  e.preventDefault(); if(busy)return;
  const files=[...$('files').files]; if(!files.length)return;
  const selectedTeam=$('upload-team').value, useAI=$('use-ai').checked;
  busy=true; $('upload-submit').disabled=true;
  $('upload-dialog').oncancel=e=>{if(busy)e.preventDefault();};
  const results=[];
  try{
    for(let i=0;i<files.length;i++){
      const file=files[i];
      $('upload-result').textContent=`Processing ${i+1}/${files.length}: ${file.name}. ${useAI?'AI reading can take several minutes.':''}`;
      if(file.size>20*1024*1024)throw new Error(`${file.name}: maximum file size is 20 MB.`);
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read file.'));reader.readAsDataURL(file);});
      const result=await post('/api/upload',{filename:file.name,data,team:selectedTeam,use_ai:useAI});
      results.push(`${file.name}: ${result.duplicate?'already present; skipped':`${result.pages} pages saved, ${result.mapped} mapped, ${result.pending_scans} scans pending`}.`);
    }
    await load();
    $('upload-result').className='success';$('upload-result').textContent=results.join(' ');
    $('files').value='';$('file-list').innerHTML='';toast('Reviews saved. Live summaries are up to date.');
  }catch(error){$('upload-result').className='error';$('upload-result').textContent=results.join(' ')+' '+error.message;await load();}
  finally{busy=false;$('upload-submit').disabled=false;}
};
$('export').onclick=()=>{const output={...state};delete output.csrf_token;const url=URL.createObjectURL(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='pdr-feedback-workspace.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
window.addEventListener('hashchange',()=>{currentTab='summary';render();window.scrollTo(0,0);});
load().catch(error=>{$('content').innerHTML=`<div class="page-wrap"><h1>Workspace unavailable</h1><p>${esc(error.message)}</p></div>`;});
