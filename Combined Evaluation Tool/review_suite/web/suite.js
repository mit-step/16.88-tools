const tools=['pdr','cdr','esdp'];
function selectTool(tool){
  if(!tools.includes(tool))tool='pdr';
  for(const name of tools){
    const tab=document.getElementById('tab-'+name),panel=document.getElementById('panel-'+name);
    tab.setAttribute('aria-selected',String(name===tool));tab.tabIndex=name===tool?0:-1;panel.hidden=name!==tool;
    if(name===tool){const frame=panel.querySelector('iframe');if(!frame.hasAttribute('src'))frame.src=frame.dataset.src;}
  }
  document.title=tool.toUpperCase()+' · Design Review Suite';
}
for(const [i,tool] of tools.entries()){
  const tab=document.getElementById('tab-'+tool);
  tab.onclick=()=>{location.hash=tool;selectTool(tool);};
  tab.onkeydown=e=>{
    let next;if(e.key==='ArrowRight')next=(i+1)%tools.length;
    if(e.key==='ArrowLeft')next=(i+tools.length-1)%tools.length;
    if(e.key==='Home')next=0;if(e.key==='End')next=tools.length-1;
    if(next!==undefined){e.preventDefault();document.getElementById('tab-'+tools[next]).focus();location.hash=tools[next];selectTool(tools[next]);}
  };
}
window.addEventListener('hashchange',()=>selectTool(location.hash.slice(1)));
selectTool(location.hash.slice(1));
(async()=>{try{
  const response=await fetch('/api/config');if(!response.ok)throw Error();const config=await response.json();
  document.getElementById('connection').textContent=config.hosted?'Hosted workspace':'Local workspace';
  const logout=document.getElementById('logout');logout.hidden=!config.hosted;
  logout.onclick=async()=>{await fetch('/api/logout',{method:'POST',headers:{'X-Review-Token':config.csrf_token}});location.reload();};
}catch{document.getElementById('connection').textContent='Connection unavailable';}})();
