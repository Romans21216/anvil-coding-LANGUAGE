(() => {
  const demo = `# Anvil starter scene: one mixed 2D/3D world.
scene 3d
camera perspective 0 3 8
clear rgba(11, 16, 27, 255)

set var(spin) = 0.0
set var(score) = 0

fn(update)
  set var(spin) = compute(var(spin) + delta())
  if pressed(SPACE)
    add var(score) 1
  end
end

fn(draw)
  display plane(0, -1, 0, 12, 12) -rgb(33, 47, 64)
  display cube(0, 0, 0, 1.8) -rgb(88, 164, 255) -rotate(0, var(spin), 0)
  display sphere(2, 0.2, 0, 0.7) -rgb(255, 157, 91)
  display text("Anvil Engine") 1 -l(20, 24) -rgb(237, 243, 255)
  display text("Space presses: " + var(score)) 2 -l(20, 52) -rgb(157, 199, 255)
end`;
  const source = document.querySelector('#source');
  const canvas = document.querySelector('#game');
  const ctx = canvas.getContext('2d');
  const consoleBox = document.querySelector('#console');
  const overlay = document.querySelector('#overlay');
  const keyState = new Set();
  let commands = [], mode = '3d', clear = [11,16,27,255], paused = false, spin = 0, score = 0;
  let last = performance.now(), fpsWindow = last, frames = 0, fps = 60, pointer = [0,0];

  const log = (text, type='info') => {
    const row = document.createElement('div'); row.className = `console-line ${type}`; row.textContent = text; consoleBox.append(row);
    consoleBox.scrollTop = consoleBox.scrollHeight;
    document.querySelector('#message-count').textContent = `${consoleBox.querySelectorAll('.console-line').length} messages`;
  };
  const splitArgs = (s) => { const out=[]; let depth=0, quote='', part=''; for(let i=0;i<s.length;i++){const c=s[i]; if(quote){part+=c;if(c==='\\'&&i+1<s.length)part+=s[++i];else if(c===quote)quote='';continue;} if(c==='"'||c==="'"){quote=c;part+=c;} else if(c==='('){depth++;part+=c;} else if(c===')'){depth--;part+=c;} else if(c===','&&depth===0){out.push(part.trim());part='';}else part+=c;} if(part.trim())out.push(part.trim()); return out; };
  const num = x => Number.parseFloat(x) || 0;
  const rgba = c => `rgba(${c[0]|0},${c[1]|0},${c[2]|0},${(c[3]??255)/255})`;
  function parseColor(line){const m=line.match(/-rgba?\(([^)]*)\)/);return m?splitArgs(m[1]).map(num).concat(m[1].split(',').length===3?[255]:[]).slice(0,4):[180,190,210,255];}
  function parse(){
    const lines=source.value.split(/\r?\n/); commands=[]; mode='3d'; clear=[11,16,27,255];
    for(let n=0;n<lines.length;n++){const line=lines[n].trim(); if(!line||line.startsWith('#'))continue;
      const sc=line.match(/^scene\s+(2d|3d)$/i); if(sc){mode=sc[1].toLowerCase();continue;}
      const cl=line.match(/^clear\s+rgba\(([^)]*)\)/i); if(cl){clear=splitArgs(cl[1]).map(num);continue;}
      const d=line.match(/^display\s+(cube|sphere|plane|rect|circle|line|text)\(/i); if(!d)continue;
      const open=d[0].length-1;let depth=0,quote='',close=-1;
      for(let i=open;i<line.length;i++){const ch=line[i];if(quote){if(ch==='\\')i++;else if(ch===quote)quote='';continue;}if(ch==='"'||ch==="'"){quote=ch;continue;}if(ch==='(')depth++;else if(ch===')'&&--depth===0){close=i;break;}}
      if(close<0)throw new Error(`Line ${n+1}: unclosed display command`);
      const kind=d[1].toLowerCase(), args=splitArgs(line.slice(open+1,close)), tail=line.slice(close+1), color=parseColor(tail), pos=tail.match(/-l\(([^)]*)\)/), rot=tail.match(/-rotate\(([^)]*)\)/), layer=tail.match(/\s(\d+)\s+-l\(/);
      commands.push({kind,args,color,pos:pos?splitArgs(pos[1]).map(num):null,rot:rot?splitArgs(rot[1]).map(num):[0,0,0],animate:/var\(spin\)/.test(tail),layer:layer?Number(layer[1]):0,line:n+1});
    }
    document.querySelector('#mode-chip').textContent=mode.toUpperCase();
    overlay.classList.add('hidden');
    document.querySelector('#run-status').textContent=`Ready · ${commands.length} draw command${commands.length===1?'':'s'}`;
    return commands.length;
  }
  const project=(x,y,z)=>{const w=canvas.width,h=canvas.height, focal=540, depth=Math.max(0.3,z+8);return [w/2+x*focal/depth,h*.57-y*focal/depth,depth];};
  const shade=(c,k)=>rgba(c.map((v,i)=>i<3?Math.max(0,Math.min(255,v*k)):v));
  const rotatePoint=(p,a)=>{let [x,y,z]=p;const [rx,ry,rz]=a.map(v=>v*Math.PI/180);let q=[x,y*Math.cos(rx)-z*Math.sin(rx),y*Math.sin(rx)+z*Math.cos(rx)];[x,y,z]=q;q=[x*Math.cos(ry)+z*Math.sin(ry),y,-x*Math.sin(ry)+z*Math.cos(ry)];[x,y,z]=q;return [x*Math.cos(rz)-y*Math.sin(rz),x*Math.sin(rz)+y*Math.cos(rz),z];};
  function drawCube(c){const a=c.args.map(num),size=a[3]||1,half=size/2,rotation=c.animate?[0,spin%360,0]:c.rot,pts=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]].map(p=>rotatePoint(p.map(v=>v*half),rotation).map((v,i)=>v+a[i]));const faces=[[0,1,2,3],[5,4,7,6],[4,0,3,7],[1,5,6,2],[3,2,6,7],[4,5,1,0]];const shades=[.58,.9,.68,.78,1,.48];const polys=faces.map((f,i)=>({f,depth:f.reduce((s,j)=>s+project(...pts[j])[2],0)/4,i})).sort((a,b)=>b.depth-a.depth);for(const p of polys){const coords=p.f.map(j=>project(...pts[j]));ctx.beginPath();ctx.moveTo(coords[0][0],coords[0][1]);coords.slice(1).forEach(v=>ctx.lineTo(v[0],v[1]));ctx.closePath();ctx.fillStyle=shade(c.color,shades[p.i]);ctx.fill();ctx.strokeStyle='#ffffff26';ctx.lineWidth=1;ctx.stroke();}}
  function drawPlane(c){const a=c.args.map(num),x=a[0]||0,y=a[1]||0,z=a[2]||0,w=a[3]||8,d=a[4]||8;ctx.strokeStyle='#8ea8c420';ctx.lineWidth=1;for(let i=-5;i<=5;i++){for(const [p,q] of [[[x-w/2,y,z+i*d/10],[x+w/2,y,z+i*d/10]],[[x+i*w/10,y,z-d/2],[x+i*w/10,y,z+d/2]]]){const u=project(...p),v=project(...q);ctx.beginPath();ctx.moveTo(u[0],u[1]);ctx.lineTo(v[0],v[1]);ctx.stroke();}}}
  function drawSphere(c){const a=c.args.map(num),p=project(a[0]||0,a[1]||0,a[2]||0),r=(a[3]||.5)*540/p[2];const g=ctx.createRadialGradient(p[0]-r*.35,p[1]-r*.4,r*.05,p[0],p[1],r);g.addColorStop(0,shade(c.color,1.35));g.addColorStop(.65,rgba(c.color));g.addColorStop(1,shade(c.color,.45));ctx.beginPath();ctx.arc(p[0],p[1],r,0,Math.PI*2);ctx.fillStyle=g;ctx.fill();}
  function draw2d(c){const a=c.args, color=rgba(c.color), l=c.pos||a.slice(0,2).map(num);ctx.fillStyle=color;ctx.strokeStyle=color;ctx.lineWidth=num(a[4])||2;
    if(c.kind==='text'){let value=a[0]||'Text';const interpolated=value.match(/^['"](.*)['"]\s*\+\s*var\(score\)$/);value=interpolated?interpolated[1]+score:value.replace(/^['"]|['"]$/g,'').replace(/var\(score\)/g,String(score));ctx.font='600 20px Segoe UI, sans-serif';ctx.fillText(value,l[0],l[1]);}
    else if(c.kind==='rect'){ctx.fillRect(num(a[0]),num(a[1]),num(a[2]),num(a[3]));}
    else if(c.kind==='circle'){ctx.beginPath();ctx.arc(num(a[0]),num(a[1]),num(a[2]),0,Math.PI*2);ctx.fill();}
    else if(c.kind==='line'){ctx.beginPath();ctx.moveTo(num(a[0]),num(a[1]));ctx.lineTo(num(a[2]),num(a[3]));ctx.stroke();}
  }
  function render(){const w=canvas.width,h=canvas.height;ctx.fillStyle=rgba(clear);ctx.fillRect(0,0,w,h);
    if(mode==='3d'){const g=ctx.createLinearGradient(0,0,0,h);g.addColorStop(0,'#172438');g.addColorStop(.64,'#111b28');g.addColorStop(.641,'#121c28');g.addColorStop(1,'#101720');ctx.fillStyle=g;ctx.fillRect(0,0,w,h);ctx.fillStyle='#ceddf20a';ctx.beginPath();ctx.ellipse(w/2,h*.58,300,60,0,0,Math.PI*2);ctx.fill();}
    const sorted=[...commands].sort((a,b)=>a.layer-b.layer);for(const c of sorted){if(c.kind==='cube')drawCube(c);else if(c.kind==='plane')drawPlane(c);else if(c.kind==='sphere')drawSphere(c);else if(c.kind==='text'||c.kind==='rect'||c.kind==='circle'||c.kind==='line')draw2d(c);}
    if(mode==='3d'){ctx.strokeStyle='#cbd8ea33';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(w/2-7,h*.57);ctx.lineTo(w/2+7,h*.57);ctx.moveTo(w/2,h*.57-7);ctx.lineTo(w/2,h*.57+7);ctx.stroke();}
  }
  function loop(now){const dt=Math.min((now-last)/1000,.05);last=now;if(!paused){spin+=dt*65;render();}frames++;if(now-fpsWindow>600){fps=Math.round(frames*1000/(now-fpsWindow));document.querySelector('#fps').textContent=`${fps} FPS`;frames=0;fpsWindow=now;}requestAnimationFrame(loop);}
  function run(){consoleBox.innerHTML='';try{const count=parse();spin=0;score=0;log(`Parsed ${count} display command${count===1?'':'s'} · ${mode} scene`);log('Preview mode reads scene and display declarations; native compilation is in development.','output');render();}catch(e){overlay.textContent=e.message;overlay.classList.remove('hidden');log(e.message,'error');}}
  source.value=demo;
  const syncLines=()=>{document.querySelector('#line-numbers').textContent=Array.from({length:source.value.split('\n').length},(_,i)=>i+1).join('\n');};
  source.addEventListener('input',syncLines);source.addEventListener('scroll',()=>{document.querySelector('#line-numbers').scrollTop=source.scrollTop;});
  source.addEventListener('click',cursor);source.addEventListener('keyup',cursor);
  function cursor(){const before=source.value.slice(0,source.selectionStart).split('\n');document.querySelector('#cursor-status').textContent=`Ln ${before.length}, Col ${before[before.length-1].length+1}`;}
  document.querySelector('#run-button').addEventListener('click',run);
  document.querySelector('#reset-button').addEventListener('click',()=>{source.value=demo;syncLines();run();});
  document.querySelector('#pause-button').addEventListener('click',e=>{paused=!paused;e.currentTarget.textContent=paused?'▶ Resume':'Ⅱ Pause';document.querySelector('#run-status').textContent=paused?'Paused':'Running';});
  document.querySelector('#fullscreen-button').addEventListener('click',()=>document.querySelector('.preview-panel').requestFullscreen?.());
  document.querySelector('#clear-console').addEventListener('click',()=>{consoleBox.innerHTML='';document.querySelector('#message-count').textContent='0 messages';});
  document.querySelector('#help-button').addEventListener('click',()=>document.querySelector('#help-dialog').showModal());
  window.addEventListener('keydown',e=>{keyState.add(e.code);if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();run();}if(e.code==='Space'&&document.activeElement!==source){score++;e.preventDefault();render();}});
  window.addEventListener('keyup',e=>keyState.delete(e.code));
  canvas.addEventListener('pointermove',e=>{const r=canvas.getBoundingClientRect();pointer=[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height];});
  syncLines();run();requestAnimationFrame(loop);
})();

