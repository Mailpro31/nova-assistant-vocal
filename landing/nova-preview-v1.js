const intro=document.getElementById('intro');
const count=document.getElementById('count');
const enter=document.getElementById('enter');
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp=(n,min=0,max=1)=>Math.min(max,Math.max(min,n));

document.body.style.overflow='hidden';
let loaded=false;
let opened=false;

function finishLoading(){
  if(loaded)return;
  loaded=true;
  count.textContent='100 %';
  count.style.setProperty('--load',1);
  intro.classList.add('loaded');
  setTimeout(()=>enter.focus({preventScroll:true}),120);
}

if(reduce){
  finishLoading();
}else{
  const start=performance.now();
  const duration=980;
  const tick=now=>{
    const p=clamp((now-start)/duration);
    const eased=1-Math.pow(1-p,3);
    const value=Math.min(100,Math.round(eased*100));
    count.textContent=value+' %';
    count.style.setProperty('--load',value/100);
    if(p<1)requestAnimationFrame(tick);else finishLoading();
  };
  requestAnimationFrame(tick);
}

function openExperience(){
  if(opened||!loaded)return;
  opened=true;
  intro.classList.add('leaving');
  setTimeout(()=>{
    intro.classList.add('done');
    document.body.classList.add('ready');
    document.body.style.overflow='';
    const words=document.querySelector('.words');
    if(words)requestAnimationFrame(()=>words.classList.add('words-live'));
  },650);
}
enter.addEventListener('click',openExperience);
intro.addEventListener('click',e=>{if(e.target===intro&&loaded)openExperience()});
addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&loaded&&!opened){e.preventDefault();openExperience()}});
if(reduce)openExperience();

const revealObserver=new IntersectionObserver(entries=>{
  for(const entry of entries){
    if(!entry.isIntersecting)continue;
    entry.target.classList.add('in');
    if(entry.target.id==='pixels')entry.target.classList.add('play');
    revealObserver.unobserve(entry.target);
  }
},{threshold:.13,rootMargin:'0px 0px -5%'});
document.querySelectorAll('.reveal,#pixels').forEach(el=>revealObserver.observe(el));

const chapters=[...document.querySelectorAll('.chapter')];
const dots=[...document.querySelectorAll('.dots a')];
const experience=document.querySelector('.experience');
const chapterObserver=new IntersectionObserver(entries=>{
  for(const entry of entries){
    if(!entry.isIntersecting)continue;
    const index=chapters.indexOf(entry.target);
    dots.forEach((dot,i)=>dot.classList.toggle('on',i===index));
  }
},{threshold:.56});
chapters.forEach(chapter=>chapterObserver.observe(chapter));
if(experience){
  new IntersectionObserver(([entry])=>document.body.classList.toggle('story-active',entry.isIntersecting),{threshold:.04}).observe(experience);
}

const cinema=document.querySelector('.cinema');
const cinemaMedia=document.querySelector('.cinema-media');
const cinemaCopy=document.querySelector('.cinema-copy');
const manifest=document.querySelector('.manifesto');
let ticking=false;
function updateMotion(){
  ticking=false;
  if(!cinema||!cinemaMedia||reduce)return;
  const rect=cinema.getBoundingClientRect();
  const travel=Math.max(1,cinema.offsetHeight-innerHeight);
  const progress=clamp(-rect.top/travel);
  const morph=clamp((progress-.58)/.42);
  const ease=1-Math.pow(1-morph,3);
  const scale=1-ease*.76;
  const shift=ease*16;
  cinemaMedia.style.transform=`translate3d(0,${shift}vh,0) scale(${scale})`;
  cinemaMedia.style.borderRadius=`${ease*58}px`;
  if(cinemaCopy){
    const opacity=clamp(1-morph*1.45);
    cinemaCopy.style.opacity=opacity;
    cinemaCopy.style.transform=`translate3d(0,${-morph*22}px,0)`;
  }
  if(manifest){
    const mrect=manifest.getBoundingClientRect();
    const entering=clamp(1-mrect.top/innerHeight);
    manifest.style.setProperty('--manifest-enter',entering);
  }
}
function requestMotion(){
  if(ticking)return;
  ticking=true;
  requestAnimationFrame(updateMotion);
}
addEventListener('scroll',requestMotion,{passive:true});
addEventListener('resize',requestMotion,{passive:true});
requestMotion();

if(!reduce){
  let tx=0,ty=0,cx=0,cy=0;
  const topScene=document.getElementById('top');
  addEventListener('pointermove',e=>{
    tx=(e.clientX/innerWidth-.5)*15;
    ty=(e.clientY/innerHeight-.5)*10;
  },{passive:true});
  const drift=()=>{
    cx+=(tx-cx)*.055;
    cy+=(ty-cy)*.055;
    if(topScene)topScene.style.setProperty('--px',`${cx}px`),topScene.style.setProperty('--py',`${cy}px`);
    requestAnimationFrame(drift);
  };
  requestAnimationFrame(drift);
}

const langBtn=document.getElementById('langBtn');
if(langBtn){
  langBtn.addEventListener('click',()=>{
    const english=document.body.classList.toggle('english');
    langBtn.firstChild.nodeValue=english?'FR':'EN';
    document.documentElement.lang=english?'en':'fr';
  });
}

const soundBtn=document.getElementById('soundBtn');
if(soundBtn){
  soundBtn.addEventListener('click',()=>{
    const calm=document.body.classList.toggle('calm');
    soundBtn.style.opacity=calm?'.55':'1';
    soundBtn.setAttribute('aria-pressed',String(calm));
  });
}

dots.forEach((dot,index)=>dot.addEventListener('click',()=>dots.forEach((d,i)=>d.classList.toggle('on',i===index))));

const polishScript=document.createElement('script');
polishScript.src='/nova-preview-polish.js?v=3';
polishScript.defer=true;
document.body.appendChild(polishScript);

const compactScript=document.createElement('script');
compactScript.src='/nova-compact-ui.js?v=1';
compactScript.defer=true;
document.body.appendChild(compactScript);

const tekiyoRefineScript=document.createElement('script');
tekiyoRefineScript.src='/nova-tekiyo-refine.js?v=2';
tekiyoRefineScript.defer=true;
document.body.appendChild(tekiyoRefineScript);

const directScrollFixScript=document.createElement('script');
directScrollFixScript.src='/nova-scroll-buttons-fix.js?v=3';
directScrollFixScript.defer=true;
document.body.appendChild(directScrollFixScript);

const founderEmbedScript=document.createElement('script');
founderEmbedScript.src='/nova-founder-embedded.js?v=1';
founderEmbedScript.defer=true;
document.body.appendChild(founderEmbedScript);
