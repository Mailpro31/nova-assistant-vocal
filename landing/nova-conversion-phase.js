const demoData={
  slack:{label:'Slack / Direct message',title:'Fast, natural, ready to send.',text:'Hey Lucas — could you send me the file when you get a minute? Thanks!'},
  email:{label:'Email / New message',title:'Polished without sounding artificial.',text:'Hi Lucas,\n\nCould you send me the file when you have a moment?\n\nThanks in advance.'},
  task:{label:'Task / Project board',title:'The same thought, now actionable.',text:'Send the file\nOwner: Lucas\nPriority: Normal'}
};

const demo=document.querySelector('[data-context-demo]');
if(demo){
  const tabs=[...demo.querySelectorAll('[role="tab"]')];
  const output=demo.querySelector('.demo-output');
  const label=demo.querySelector('[data-demo-label]');
  const title=demo.querySelector('[data-demo-title]');
  const text=demo.querySelector('[data-demo-text]');
  const source=demo.querySelector('.demo-source');
  const replay=demo.querySelector('[data-demo-replay]');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cycle;

  function selectDemo(key,userInitiated=false){
    const next=demoData[key];
    if(!next)return;
    tabs.forEach(tab=>{
      const active=tab.dataset.demoTarget===key;
      tab.setAttribute('aria-selected',String(active));
      tab.tabIndex=active?0:-1;
      if(active)output.setAttribute('aria-labelledby',tab.id);
    });
    output.classList.remove('is-changing');
    void output.offsetWidth;
    label.textContent=next.label;
    title.textContent=next.title;
    text.textContent=next.text;
    output.classList.add('is-changing');
    if(userInitiated)emitNovaEvent('demo_context_change',{context:key});
  }

  function restartCycle(){
    clearInterval(cycle);
    if(reduced)return;
    cycle=setInterval(()=>{
      const current=tabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');
      selectDemo(tabs[(current+1)%tabs.length].dataset.demoTarget);
    },5200);
  }

  tabs.forEach((tab,index)=>{
    tab.addEventListener('click',()=>{selectDemo(tab.dataset.demoTarget,true);restartCycle()});
    tab.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
      event.preventDefault();
      const direction=event.key==='ArrowRight'?1:-1;
      const next=tabs[(index+direction+tabs.length)%tabs.length];
      next.focus();next.click();
    });
  });
  replay.addEventListener('click',()=>{
    source.classList.remove('is-replaying');
    void source.offsetWidth;
    source.classList.add('is-replaying');
    const active=tabs.find(tab=>tab.getAttribute('aria-selected')==='true');
    setTimeout(()=>selectDemo(active.dataset.demoTarget),reduced?0:650);
    emitNovaEvent('demo_play',{context:'voice_sample'});
    restartCycle();
  });
  restartCycle();
}

const personalPricing=document.querySelector('[data-personal-pricing]');
if(personalPricing){
  const offers={
    annual:{
      pro:{price:'49 €',href:'https://buy.stripe.com/3cI6oG7gCg5k0y3090efC0a'},
      ultra:{price:'149 €',href:'https://buy.stripe.com/6oUeVc1Wi4mCcgLaNEefC0c'},
      period:'/ year',note:'2 months free'
    },
    monthly:{
      pro:{price:'4.99 €',href:'https://buy.stripe.com/9B68wO1Wif1g3Kfg7YefC09'},
      ultra:{price:'14.99 €',href:'https://buy.stripe.com/4gM28qfN8aL0cgL4pgefC0b'},
      period:'/ month',note:'Cancel anytime'
    }
  };
  const billingButtons=[...personalPricing.querySelectorAll('[data-personal-billing]')];
  function setBilling(period,userInitiated=false){
    const offer=offers[period];
    billingButtons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.personalBilling===period)));
    ['pro','ultra'].forEach(plan=>{
      personalPricing.querySelector(`[data-plan-price="${plan}"]`).textContent=offer[plan].price;
      personalPricing.querySelector(`[data-plan-note="${plan}"]`).textContent=offer.note;
      const checkout=personalPricing.querySelector(`[data-plan-checkout="${plan}"]`);
      checkout.href=offer[plan].href;
      checkout.dataset.billing=period;
    });
    personalPricing.querySelectorAll('[data-plan-period]').forEach(element=>element.textContent=offer.period);
    if(userInitiated)emitNovaEvent('billing_change',{billing:period});
  }
  billingButtons.forEach(button=>button.addEventListener('click',()=>setBilling(button.dataset.personalBilling,true)));
  setBilling('annual');
}

function emitNovaEvent(name,properties={}){
  const detail={event:name,page:location.pathname,...properties};
  window.dispatchEvent(new CustomEvent('nova:conversion',{detail}));
  if(Array.isArray(window.dataLayer))window.dataLayer.push(detail);
}

document.querySelectorAll('a').forEach(link=>{
  const href=link.getAttribute('href')||'';
  let eventName=link.dataset.novaEvent||'';
  if(!eventName&&href.includes('Nova-Setup.exe'))eventName='download_click';
  if(!eventName&&href.includes('Nova%20Campus%20Pilot'))eventName='campus_pilot_click';
  if(!eventName&&href.includes('Nova%20Business%20Demo'))eventName='business_demo_click';
  if(!eventName&&href.includes('Nova%20Organization%20Demo'))eventName='organization_demo_click';
  if(!eventName&&href.includes('/privacy-by-design'))eventName='privacy_story_click';
  if(!eventName&&href==='/privacy.html')eventName='privacy_policy_click';
  if(!eventName&&href.includes('/personal'))eventName='personal_cta';
  if(eventName)link.addEventListener('click',()=>emitNovaEvent(eventName,{label:link.textContent.trim(),plan:link.dataset.planCheckout||link.dataset.plan||undefined,billing:link.dataset.billing||undefined}));
});

const observedEvents=[['#tarifs','pricing_view'],['[data-personal-pricing]','pricing_view'],['#local','security_view'],['.privacy-section','security_view'],['.privacy-choice','privacy_story_view']];
observedEvents.forEach(([selector,eventName])=>{
  const element=document.querySelector(selector);
  if(!element)return;
  new IntersectionObserver(([entry],observer)=>{
    if(!entry.isIntersecting)return;
    emitNovaEvent(eventName);
    observer.disconnect();
  },{threshold:.35}).observe(element);
});
