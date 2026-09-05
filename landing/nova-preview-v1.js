const intro=document.getElementById('intro');
const count=document.getElementById('count');
const enter=document.getElementById('enter');
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const mobileCinema=matchMedia('(max-width: 768px)').matches;
const clamp=(n,min=0,max=1)=>Math.min(max,Math.max(min,n));

/* Enter the experience immediately. The original intro remains in the DOM so
   the established visual system can keep evolving without a loading gate. */
intro.classList.add('done');
intro.style.display='none';
document.body.classList.add('ready');
document.body.style.overflow='';
let loaded=true;
let opened=true;

function finishLoading(){}
function openExperience(){}
const openingWords=document.querySelector('.words');
if(openingWords)requestAnimationFrame(()=>openingWords.classList.add('words-live'));
addEventListener('pageshow',e=>{if(e.persisted)location.reload()});

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
  if(!cinema||!cinemaMedia)return;

  /* Mobile has its own deterministic layout. Never let the desktop sticky/morph
     system write inline transforms or opacity there — this was the source of
     the occasional blank pastel block during iOS loading/restoration. */
  if(mobileCinema){
    cinemaMedia.style.removeProperty('transform');
    cinemaMedia.style.removeProperty('border-radius');
    if(cinemaCopy){
      cinemaCopy.style.removeProperty('opacity');
      cinemaCopy.style.removeProperty('transform');
    }
    return;
  }

  if(reduce)return;
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

/* nova-preview-polish.js, nova-compact-ui.js, nova-tekiyo-refine.js,
   nova-scroll-buttons-fix.js, nova-final-fixes.js
   and nova-founder-polish.js used to be injected here at runtime (a 2-level
   waterfall discovered only after this script executed, plus a duplicate,
   stale nova-mobile.css?v=6 re-fetch that could shadow the real ?v=8 one).
   They're now static <link>/<script defer> tags in index.html's <head>, so
   the browser can fetch everything in parallel from the start. */
