const $=id=>document.getElementById(id);
let RP = null, rpTimer = null, followingLive = true, liveActive = false, currentLive = null;
let chosen = null, frameIndex = 0, owners = null, focusPending = true, hoverPosition = null;
const COL = ['#0b1d2e', '#4b5563', '#4ade80', '#60a5fa', '#f87171'];
const buildings = {City:'V',Port:'P','Defense Post':'D',Factory:'U','SAM Launcher':'S','Missile Silo':'M'};
const ships = {Warship:'G',Transport:'T','Trade Ship':'C',Train:'R'};
const weapons = {'Atom Bomb':'A','Hydrogen Bomb':'H',MIRV:'M','MIRV Warhead':'M',SAMMissile:'S',Shell:'O'};
function color(code) {
  if (code < 2) return COL[code];
  if (code === RP.self) return COL[2];
  return 'hsl('+Math.round((code * 137.508) % 360)+' 78% '+(49 + code % 4 * 6)+'%)';
}
function stopReplay() {
  clearInterval(rpTimer);
  rpTimer = null;
  $('rpPlay').textContent = 'Lecture';
}
function rpDraw(i) {
  if (!RP) return;
  frameIndex = i;
  const f = RP.frames[i], c = $('rpCanvas'), d = c.getContext('2d');
  const w = RP.gw, h = RP.gh, sx = c.width/w, sy = c.height/h;
  function drawRun(start, size, fill) {
    d.fillStyle = fill;
    while (size > 0) {
      const x = start % w, y = Math.floor(start/w), n = Math.min(size,w-x);
      d.fillRect(x*sx,y*sy,n*sx,sy);
      start += n; size -= n;
    }
  }
  owners = null;
  if (f.owners) {
    owners = new Uint16Array(w*h);
    const packed = atob(f.owners);
    let offset = 0;
    for (let p = 0; p + 3 < packed.length; p += 4) {
      const size = packed.charCodeAt(p) + 256 * packed.charCodeAt(p+1);
      const code = packed.charCodeAt(p+2) + 256 * packed.charCodeAt(p+3);
      if (!size || offset+size > w*h) break;
      owners.fill(code,offset,offset+size);
      drawRun(offset,size,color(code)); offset += size;
    }
    if (chosen !== null) {
      d.beginPath();
      for (let tile = 0; tile < owners.length; tile++) {
        if (owners[tile] !== chosen) continue;
        const x = tile%w, y = Math.floor(tile/w);
        if (x === 0 || owners[tile-1] !== chosen) { d.moveTo(x*sx,y*sy); d.lineTo(x*sx,(y+1)*sy); }
        if (x+1 === w || owners[tile+1] !== chosen) { d.moveTo((x+1)*sx,y*sy); d.lineTo((x+1)*sx,(y+1)*sy); }
        if (y === 0 || owners[tile-w] !== chosen) { d.moveTo(x*sx,y*sy); d.lineTo((x+1)*sx,y*sy); }
        if (y+1 === h || owners[tile+w] !== chosen) { d.moveTo(x*sx,(y+1)*sy); d.lineTo((x+1)*sx,(y+1)*sy); }
      }
      d.strokeStyle = '#06151c'; d.lineWidth = 4; d.stroke();
      d.strokeStyle = '#f5fff8'; d.lineWidth = 1.8; d.stroke();
    }
    {
      const visible = {...($('rpBuildings').checked ? buildings : {}),
                       ...($('rpShips').checked ? ships : {}),
                       ...($('rpWeapons').checked ? weapons : {})};
      const radius = Math.max(8,c.width/175), used = new Set();
      d.font = 'bold '+Math.round(radius*1.3)+'px system-ui';
      d.textAlign = 'center'; d.textBaseline = 'middle';
      const units = (f.buildings || []).filter(u=>Object.hasOwn(visible,u[1])).sort(
        (a,b) => Number(Object.hasOwn(weapons,b[1])) - Number(Object.hasOwn(weapons,a[1]))
          || (b[0] === RP.self) - (a[0] === RP.self));
      for (const [owner,kind,x,y] of units) {
        const px = x*c.width/RP.mw, py = y*c.height/RP.mh;
        const cell = Math.round(px/(radius*2))+','+Math.round(py/(radius*2));
        if (used.has(cell)) continue;
        used.add(cell);
        d.beginPath();
        if (Object.hasOwn(weapons,kind)) {
          d.moveTo(px,py-radius); d.lineTo(px+radius,py);
          d.lineTo(px,py+radius); d.lineTo(px-radius,py); d.closePath();
        } else if (Object.hasOwn(ships,kind)) d.rect(px-radius,py-radius,radius*2,radius*2);
        else d.arc(px,py,radius,0,Math.PI*2);
        d.fillStyle = color(owner); d.fill();
        d.strokeStyle = '#0b1420'; d.lineWidth = 2.5; d.stroke();
        d.fillStyle = '#07101a'; d.fillText(visible[kind],px,py+0.5);
      }
    }
  } else {
    for (let p = 0; p < w*h; p++) drawRun(p,1,COL[Number(f.grid[p])] || COL[0]);
  }
  $('rpInfo').textContent = (liveActive ? 'Direct' : 'Image '+(i+1)+'/'+RP.frames.length)+' | Tick '+f.tick+
    ' | Tuiles '+f.tiles+' | Troupes '+f.troops+' | Or '+f.gold+' | Adversaires '+f.others+
    (f.buildings ? ' | Batiments et unites '+f.buildings.length : '')+' | Issue '+RP.end;
  const stats = [...(f.stats || [])].filter(p=>p[5]).sort((a,b)=>(b[0]===RP.self)-(a[0]===RP.self) || b[2]-a[2]);
  $('playerRows').replaceChildren(...stats.map(([code,name,tiles,troops,gold,alive,ally])=>{
    const row=document.createElement('tr'), nameCell=document.createElement('td');
    const button=document.createElement('button');
    button.className='player-name';
    button.textContent=name+(code===RP.self?' (mon IA)':ally?' (allié)':'');
    button.style.color=color(code);
    button.onclick=()=>selectPlayer(code,true);
    nameCell.append(button); row.append(nameCell);
    row.classList.toggle('picked',code===chosen);
    for (const value of [tiles,troops,gold]) {
      const cell=document.createElement('td');
      cell.textContent=value.toLocaleString('fr-FR');
      row.append(cell);
    }
    return row;
  }));
  const selected=(f.stats || []).find(p=>p[0]===chosen);
  const selectedName=(RP.players || []).find(p=>p[0]===chosen)?.[1];
  $('playerFocus').textContent=selected ? selected[1]+(chosen===RP.self?' · Mon IA':'')+
    ' | '+selected[2].toLocaleString('fr-FR')+' tuiles · '+selected[3].toLocaleString('fr-FR')+
    ' troupes · '+selected[4].toLocaleString('fr-FR')+' or' : selectedName || 'Clique sur un pays pour le sélectionner.';
  if (focusPending && focusPlayer(chosen, true)) focusPending=false;
  if (hoverPosition) inspectAt(hoverPosition);
  const labels = new Map((f.stats || []).map(p=>[p[7],p[1]]));
  const attacks = (f.outgoing || []).map(a=>'→ '+(labels.get(a.target)||'Territoire neutre')+' · '+a.troops+' troupes');
  const incoming = (f.incoming || []).map(a=>'← '+(labels.get(a.from)||'Adversaire')+' · '+a.troops+' troupes');
  $('battleSummary').textContent = [...attacks,...incoming].slice(0,12).join(' | ') || 'Aucun combat actif enregistré.';
  const history=liveActive ? (RP.history || []) : RP.frames.slice(Math.max(0,i-40),i+1).filter(x=>x.actions?.length);
  $('actionHistory').replaceChildren(...history.slice(-10).reverse().map(item=>{
    const li=document.createElement('li');
    li.textContent='Tick '+item.tick+' · '+item.actions.join(', ');
    return li;
  }));
}
function showReplay(data, live) {
  const previously = RP?.name;
  RP = data;
  if (previously !== RP.name) {
    chosen=RP.self ?? null;
    focusPending=true;
    hoverPosition=null; $('mapTip').hidden=true;
    applyZoom(100);
  } else if (focusPending && chosen===null && RP.self!=null) chosen=RP.self;
  liveActive = live;
  const canvas = $('rpCanvas');
  const width = RP.gw*8, height = RP.gh*8;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width; canvas.height = height;
  }
  $('rpPlay').disabled = $('rpSlider').disabled = live;
  $('liveBadge').hidden = !live;
  if (!live || previously !== RP.name) {
    stopReplay();
    const list = $('rpOwners');
    list.replaceChildren();
    for (const [code,name] of RP.players || []) {
      const item = document.createElement('span');
      item.style.color = color(code);
      item.textContent = (code === RP.self ? 'Moi : ' : '')+name;
      list.append(item);
    }
    $('rpLegend').hidden = !RP.players;
    for (const id of ['rpBuildings','rpShips','rpWeapons']) $(id).disabled = !RP.players;
  }
  const slider = $('rpSlider');
  slider.max = RP.frames.length-1; slider.value = 0;
  rpDraw(0);
}
async function rpLoad(n) {
  if (!n) return;
  stopReplay();
  const response = await fetch('/api/replay?name='+encodeURIComponent(n));
  if (!response.ok || $('rp').value !== n) return;
  const data = await response.json();
  if ($('rp').value !== n || !data.frames.length) return;
  if (followingLive && currentLive) return;
  showReplay(data,false);
}
async function rpList() {
  const response = await fetch('/api/replays');
  if (!response.ok) return;
  const replays = await response.json(), select = $('rp');
  const names = replays.map(r => r.name);
  if (names.join('|') === Array.from(select.options,o => o.value).join('|')) return;
  const selected = names.includes(select.value) ? select.value : names[0];
  const previous = select.value;
  select.replaceChildren(...replays.map(r => new Option(r.map ? r.map+' - '+r.name : r.name,r.name)));
  if (selected) {
    select.value = selected;
    if ((!followingLive || !currentLive) && (!RP || selected !== previous)) rpLoad(selected);
  }
}
$('rp').onchange = event => {followingLive=false;rpLoad(event.target.value)};
$('rpLive').onclick = () => {followingLive=true;liveCursor='';pollLive()};
const viewport=$('mapViewport'), mapCanvas=$('rpCanvas');
let drag=null;
function applyZoom(value) {
  $('rpZoom').value=value;
  $('rpCanvas').style.width=value+'%';
}
function focusPlayer(code, zoom) {
  if (!RP || !owners || code===null) return false;
  let sumX=0,sumY=0,count=0;
  for(let p=0;p<owners.length;p++) {
    if(owners[p]!==code) continue;
    sumX+=p%RP.gw+0.5; sumY+=Math.floor(p/RP.gw)+0.5; count++;
  }
  if (!count) return false;
  if (zoom && Number($('rpZoom').value)<165) applyZoom(165);
  viewport.scrollLeft=sumX/count/RP.gw*mapCanvas.clientWidth-viewport.clientWidth/2;
  viewport.scrollTop=sumY/count/RP.gh*mapCanvas.clientHeight-viewport.clientHeight/2;
  return true;
}
function selectPlayer(code, zoom) {
  chosen=code;
  focusPending=false;
  if (zoom) focusPlayer(code,true);
  rpDraw(frameIndex);
}
function inspectAt(point) {
  const tip=$('mapTip');
  if (!RP || !owners) {tip.hidden=true;return null;}
  const bounds=mapCanvas.getBoundingClientRect();
  const x=(point.x-bounds.left)/bounds.width, y=(point.y-bounds.top)/bounds.height;
  if (!(x>=0 && x<1 && y>=0 && y<1)) {tip.hidden=true;return null;}
  const code=owners[Math.floor(y*RP.gh)*RP.gw+Math.floor(x*RP.gw)];
  const frame=RP.frames[frameIndex], row=(frame.stats || []).find(p=>p[0]===code);
  const name=code===0?'Mer':code===1?'Territoire neutre':row?.[1]||(RP.players||[]).find(p=>p[0]===code)?.[1]||'Joueur';
  const nearby=(frame.buildings || []).find(unit=>
    Math.hypot((unit[2]/RP.mw-x)*bounds.width,(unit[3]/RP.mh-y)*bounds.height)<11);
  const lines=[name+(code===RP.self?' · Mon IA':row?.[6]?' · Allié':'')];
  if(row) lines.push(row[2].toLocaleString('fr-FR')+' tuiles',row[3].toLocaleString('fr-FR')+' troupes · '+row[4].toLocaleString('fr-FR')+' or');
  if(nearby) lines.push(nearby[1]+' · niveau '+nearby[4]);
  tip.textContent=lines.join('\n');tip.hidden=false;
  tip.style.left=Math.max(4,Math.min(point.x+14,window.innerWidth-tip.offsetWidth-8))+'px';
  tip.style.top=Math.max(4,Math.min(point.y+14,window.innerHeight-tip.offsetHeight-8))+'px';
  return code;
}
$('rpSelf').onclick=()=>{if (RP?.self!=null) selectPlayer(RP.self,true)};
$('rpFit').onclick=()=>{focusPending=false;applyZoom(100);viewport.scrollTo(0,0)};
$('rpZoom').oninput = e=>{focusPending=false;applyZoom(e.target.value)};
viewport.onpointerdown=e=>{
  if (e.button!==0 || e.target!==mapCanvas) return;
  drag=[e.clientX,e.clientY,viewport.scrollLeft,viewport.scrollTop,false];
  viewport.setPointerCapture(e.pointerId);
};
viewport.onpointermove=e=>{
  if (drag && (drag[4] || Math.hypot(e.clientX-drag[0],e.clientY-drag[1])>5)) {
    drag[4]=true;focusPending=false;hoverPosition=null;$('mapTip').hidden=true;
    viewport.classList.add('dragging');
    viewport.scrollLeft=drag[2]+drag[0]-e.clientX;
    viewport.scrollTop=drag[3]+drag[1]-e.clientY;
    return;
  }
  hoverPosition={x:e.clientX,y:e.clientY};inspectAt(hoverPosition);
};
viewport.onpointerup=e=>{
  const clicked=drag&&!drag[4];
  drag=null;viewport.classList.remove('dragging');
  if (clicked) {
    const code=inspectAt({x:e.clientX,y:e.clientY});
    if (code>1) selectPlayer(code,false);
  }
};
viewport.onpointercancel=viewport.onpointerleave=()=>{
  drag=null;hoverPosition=null;$('mapTip').hidden=true;viewport.classList.remove('dragging');
};
$('rpSlider').oninput = event => rpDraw(+event.target.value);
for (const id of ['rpBuildings','rpShips','rpWeapons']) $(id).onchange = () => rpDraw(+$('rpSlider').value);
$('rpFull').onclick = async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await $('rpCanvas').closest('.card').requestFullscreen();
};
$('rpPlay').onclick = () => {
  if (rpTimer) { stopReplay(); return; }
  if (!RP || liveActive) return;
  const slider = $('rpSlider');
  if (+slider.value >= +slider.max) { slider.value = 0; rpDraw(0); }
  $('rpPlay').textContent = 'Pause';
  rpTimer = setInterval(() => {
    if (+slider.value >= +slider.max) { stopReplay(); return; }
    slider.value = +slider.value+1; rpDraw(+slider.value);
  }, 80 / Number($('rpSpeed').value));
};
$('rpSpeed').onchange=()=>{if(rpTimer){stopReplay();$('rpPlay').click()}};
rpList(); setInterval(rpList,8000);
let enabled = false, sending = false, opened = null, liveCursor = '', readingLive = false;
async function pollLive() {
  if (!followingLive || !currentLive || readingLive) return;
  const expected=currentLive;
  readingLive=true;
  try {
    const response=await fetch('/api/live?cursor='+encodeURIComponent(liveCursor),{cache:'no-store'});
    if (!response.ok) return;
    const data=await response.json();
    if (followingLive && expected===currentLive && data.snapshot?.name===expected) {
      liveCursor=data.cursor;
      showReplay(data.snapshot,true);
    }
  } finally { readingLive=false; }
}
const statusLine = $('statusLine'), progress = $('jobProgress');
async function pollGame() {
  try {
    const response = await fetch('/api/game', {cache:'no-store'});
    if (!response.ok) throw Error('Dashboard indisponible');
    const game = await response.json();
    $('start').disabled = !enabled || sending || game.status === 'running';
    if (currentLive !== game.live_name) liveCursor='';
    currentLive=game.live_name || null;
    $('rpLive').hidden=!currentLive;
    $('stop').hidden = game.status !== 'running' || game.stopping;
    statusLine.textContent = (game.attempt ? 'Partie '+game.attempt+' · ' : '')+game.message;
    progress.hidden = game.status !== 'running';
    if (game.limit) { progress.max = game.limit; progress.value = game.step; }
    else progress.removeAttribute('value');
    if (!currentLive && followingLive && game.replay && opened !== game.replay) {
      opened = game.replay;
      await rpList();
      $('rp').value = game.replay;
      await rpLoad(game.replay);
      refreshReports().catch(()=>{});
    }
  } catch (error) {
    statusLine.textContent = error.message;
    $('start').disabled = true;
  }
}
$('gameForm').onsubmit = async event => {
  event.preventDefault();
  if (sending) return;
  sending = true;
  $('start').disabled = true;
  const form = new FormData(event.currentTarget);
  const body = {map:form.get('map'), difficulty:form.get('difficulty'), bots:Number(form.get('bots')),
                nations:form.has('nations'), retry:form.has('retry'), seed:form.get('seed').trim(), device:form.get('device')};
  try {
    const response = await fetch('/api/game', {
      method:'POST', headers:{'Content-Type':'application/json','X-OpenFront-Session':SESSION_TOKEN},
      body:JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Impossible de lancer la partie');
    followingLive=true; liveCursor='';
    await pollGame();
    await pollLive();
  } catch (error) {
    statusLine.textContent = error.message;
    $('start').disabled = false;
    return;
  } finally {
    sending = false;
  }
};
$('stop').onclick = async () => {
  $('stop').disabled = true;
  try {
    const response = await fetch('/api/game/stop', {method:'POST',headers:{'X-OpenFront-Session':SESSION_TOKEN}});
    if (!response.ok) throw Error("Arrêt indisponible");
    await pollGame();
  } catch (error) { statusLine.textContent = error.message; }
  finally { $('stop').disabled = false; }
};
async function refreshReports() {
  const [hardware, reports] = await Promise.all([
    fetch('/api/hardware').then(r=>r.json()), fetch('/api/benchmarks').then(r=>r.json())
  ]);
  $('runtimeInfo').textContent = (hardware.processors?.map(p=>p.Name).join(', ') || hardware.cpu_fallback || '')+
    ' | PyTorch '+hardware.torch+' | '+(hardware.cuda_devices?.filter(d=>d.usable).map(d=>d.name).join(', ') || 'CPU');
  $('reportsList').replaceChildren(...reports.map(({file})=>{
    const row=document.createElement('li'), link=document.createElement('a');
    link.href='/reports/'+encodeURIComponent(file);
    link.textContent=file;
    link.download=file;
    link.style.color='#9bd9ff';
    row.append(link);return row;
  }));
}
async function setupGame() {
  try {
    const response = await fetch('/api/options');
    const options = await response.json();
    if (!response.ok || !options.maps.length) throw Error('Cartes indisponibles');
    $('gameMap').replaceChildren(...options.maps.map(([id,label])=>new Option(label,id)));
    $('gameMap').value = options.maps.some(([id])=>id==='World') ? 'World' : options.maps[0][0];
    $('deviceCuda').disabled = !options.cuda;
    enabled = true;
    await pollGame();
  } catch (error) { statusLine.textContent = error.message; }
}
setupGame();
refreshReports().catch(()=>{});
setInterval(()=>{if (enabled && !sending) pollGame()},900);
setInterval(()=>pollLive().catch(()=>{}),400);
