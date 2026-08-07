const polishLink=document.createElement('link');polishLink.rel='stylesheet';polishLink.href='/nova-preview-polish.css?v=2';document.head.appendChild(polishLink);

/* Premium interaction layer */
const finePointer=matchMedia('(hover:hover) and (pointer:fine)').matches;
const premiumButtons=[...document.querySelectorAll('.enter,.black-btn,.dock a,.dock button,.logo-top')];

if(finePointer&&!reduce){
  premiumButtons.forEach(el=>{
    el.addEventListener('pointermove',event=>{
      const r=el.getBoundingClientRect();
      const strength=el.classList.contains('circle')?5:8;
      const x=((event.clientX-r.left)/r.width-.5)*strength;
      const y=((event.clientY-r.top)/r.height-.5)*strength;
      el.style.setProperty('--mx',`${x}px`);
      el.style.setProperty('--my',`${y}px`);
    });
    el.addEventListener('pointerleave',()=>{
      el.style.setProperty('--mx','0px');
      el.style.setProperty('--my','0px');
    });
  });
}

premiumButtons.forEach(el=>{
  el.addEventListener('pointerdown',event=>{
    const r=el.getBoundingClientRect();
    const ripple=document.createElement('i');
    const size=Math.max(r.width,r.height)*1.9;
    ripple.className='press-ripple';
    ripple.style.width=ripple.style.height=`${size}px`;
    ripple.style.left=`${event.clientX-r.left}px`;
    ripple.style.top=`${event.clientY-r.top}px`;
    el.appendChild(ripple);
    setTimeout(()=>ripple.remove(),680);
  });
});

/* Stagger every editorial group instead of revealing it all at once. */
const staggerGroups=['.chapter-inner','.case-list','.plans','.faq-list'];
document.querySelectorAll(staggerGroups.join(',')).forEach(group=>{
  [...group.children].forEach((child,index)=>{
    if(child.classList.contains('reveal'))child.style.setProperty('--reveal-delay',`${Math.min(index*75,300)}ms`);
    child.querySelectorAll?.('.reveal').forEach((nested,nestedIndex)=>nested.style.setProperty('--reveal-delay',`${Math.min((nestedIndex+1)*72,360)}ms`));
  });
});

/* Add a discreet choice label without changing the pricing structure. */
const featured=document.querySelector('.plan.featured');
if(featured&&!featured.querySelector('.plan-badge')){
  const badgeFr=document.createElement('span');badgeFr.className='plan-badge fr';badgeFr.textContent='Le plus choisi';
  const badgeEn=document.createElement('span');badgeEn.className='plan-badge en';badgeEn.textContent='Most popular';
  featured.prepend(badgeEn);featured.prepend(badgeFr);
}

/* Pointer light for cards and the cinematic canvas. */
document.querySelectorAll('.plan').forEach(card=>{
  card.addEventListener('pointermove',event=>{
    const r=card.getBoundingClientRect();
    card.style.setProperty('--spot-x',`${event.clientX-r.left}px`);
    card.style.setProperty('--spot-y',`${event.clientY-r.top}px`);
  });
});
if(cinemaMedia){
  cinemaMedia.addEventListener('pointermove',event=>{
    const r=cinemaMedia.getBoundingClientRect();
    cinemaMedia.style.setProperty('--cinema-x',`${((event.clientX-r.left)/r.width)*100}%`);
    cinemaMedia.style.setProperty('--cinema-y',`${((event.clientY-r.top)/r.height)*100}%`);
  });
}

/* Scroll cue appears after the intro and disappears as soon as the user moves. */
const scrollCue=document.createElement('div');
scrollCue.className='scroll-cue';
scrollCue.innerHTML='<i></i><span class="fr">Faire défiler</span><span class="en">Scroll</span>';
document.body.appendChild(scrollCue);
let cueHidden=false;
function showCue(){if(!cueHidden){scrollCue.classList.add('show');setTimeout(()=>scrollCue.classList.remove('show'),4200)}}
const originalOpenExperience=openExperience;
openExperience=function(){
  if(opened||!loaded)return;
  document.body.classList.add('page-enter');
  originalOpenExperience();
  setTimeout(()=>{
    document.body.classList.add('page-revealed');
    showCue();
  },650);
  setTimeout(()=>document.body.classList.remove('page-enter'),1450);
};
/* Rebind because the original listener retained the old function reference. */
enter.replaceWith(enter.cloneNode(true));
const premiumEnter=document.getElementById('enter');
premiumEnter.addEventListener('click',openExperience);
premiumEnter.addEventListener('pointerdown',event=>{
  const r=premiumEnter.getBoundingClientRect();const ripple=document.createElement('i');const size=Math.max(r.width,r.height)*1.9;
  ripple.className='press-ripple';ripple.style.width=ripple.style.height=`${size}px`;ripple.style.left=`${event.clientX-r.left}px`;ripple.style.top=`${event.clientY-r.top}px`;premiumEnter.appendChild(ripple);setTimeout(()=>ripple.remove(),680);
});
if(finePointer&&!reduce){premiumEnter.addEventListener('pointermove',event=>{const r=premiumEnter.getBoundingClientRect();premiumEnter.style.setProperty('--mx',`${((event.clientX-r.left)/r.width-.5)*8}px`);premiumEnter.style.setProperty('--my',`${((event.clientY-r.top)/r.height-.5)*8}px`)});premiumEnter.addEventListener('pointerleave',()=>{premiumEnter.style.setProperty('--mx','0px');premiumEnter.style.setProperty('--my','0px')})}
intro.addEventListener('click',event=>{if(event.target===intro&&loaded)openExperience()});
addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&loaded&&!opened){event.preventDefault();openExperience()}},{capture:true});

function hideCue(){
  if(cueHidden)return;cueHidden=true;scrollCue.classList.remove('show');
}
addEventListener('wheel',hideCue,{passive:true,once:true});
addEventListener('touchmove',hideCue,{passive:true,once:true});
addEventListener('scroll',()=>{if(scrollY>28)hideCue()},{passive:true});

/* Dock becomes calmer during movement and highlights the current destination. */
const dock=document.querySelector('.dock');
let dockTimer;
addEventListener('scroll',()=>{
  dock?.classList.add('scrolling');
  clearTimeout(dockTimer);
  dockTimer=setTimeout(()=>dock?.classList.remove('scrolling'),150);
},{passive:true});
const dockLinks=[...document.querySelectorAll('.dock a[href^="#"]')];
const dockTargets=dockLinks.map(link=>document.querySelector(link.getAttribute('href'))).filter(Boolean);
if(dockTargets.length){
  const dockObserver=new IntersectionObserver(entries=>{
    entries.filter(entry=>entry.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio).slice(0,1).forEach(entry=>{
      dockLinks.forEach(link=>link.classList.toggle('active',link.getAttribute('href')===`#${entry.target.id}`));
    });
  },{threshold:[.18,.35,.6],rootMargin:'-18% 0px -45%'});
  dockTargets.forEach(target=>dockObserver.observe(target));
}

const founderPolish=document.createElement('script');founderPolish.src='/nova-founder-polish.js?v=1';founderPolish.defer=true;document.body.appendChild(founderPolish);
