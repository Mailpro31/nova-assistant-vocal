(()=>{
  document.documentElement.lang='en';
  document.body.classList.add('english');

  const legacyLang=document.getElementById('langBtn');
  if(legacyLang) legacyLang.remove();

  const style=document.createElement('style');
  style.textContent=`
    :root{
      --font:"Arial Nova","Helvetica Neue",Arial,Helvetica,sans-serif!important;
      --display:"Arial Nova","Helvetica Neue",Arial,Helvetica,sans-serif!important;
    }
    html,body{scrollbar-width:none!important;-ms-overflow-style:none!important}
    html::-webkit-scrollbar,body::-webkit-scrollbar,*::-webkit-scrollbar{width:0!important;height:0!important;display:none!important}
    body{padding-bottom:0!important;font-family:var(--font)!important;font-weight:400!important;letter-spacing:-.012em!important}
    button,a,input,textarea{font-family:var(--font)!important}

    /* Tekiyo-like editorial typography: neutral grotesk, lighter display weight, tight leading. */
    h1,h2,h3,strong,.price{font-family:var(--display)!important;color:#111217}
    .manifesto h1,.chapter h2,.usecases h2,.pricing>h2,.faq>h2,.final h2{
      font-weight:500!important;
      letter-spacing:-.065em!important;
      line-height:.92!important;
      text-wrap:balance;
    }
    .manifesto h1{font-size:clamp(48px,7.2vw,108px)!important}
    .chapter h2{font-size:clamp(48px,6.7vw,98px)!important}
    .usecases h2,.pricing>h2,.faq>h2{font-size:clamp(48px,7vw,100px)!important}
    .final h2{font-size:clamp(60px,9vw,132px)!important}
    .manifesto p,.chapter p,.usecases p,.pricing>p,.faq-item p{
      font-family:var(--font)!important;
      font-weight:400!important;
      letter-spacing:-.018em!important;
      line-height:1.55!important;
    }
    .chapter-label,.hero-note,.words span,.cinema-copy small,.num,.plan-badge{
      font-family:var(--font)!important;
      font-weight:600!important;
      letter-spacing:.16em!important;
      text-transform:uppercase!important;
    }
    .words span{font-size:clamp(10px,.85vw,12px)!important}
    .black-btn,.dock .main,.enter{font-weight:600!important;letter-spacing:-.015em!important}

    .cinema{background:radial-gradient(circle at 13% 39%,rgba(104,145,181,.91) 0,rgba(151,188,216,.87) 22%,transparent 49%),radial-gradient(circle at 81% 27%,rgba(247,227,183,.93) 0,rgba(235,216,180,.84) 23%,transparent 49%),radial-gradient(circle at 63% 82%,rgba(183,222,202,.92) 0,rgba(183,222,202,.78) 25%,transparent 54%),linear-gradient(132deg,#bed3e0 0,#dfe9e8 42%,#eee4c9 68%,#c8e1d4 100%)!important}

    .dots.chapter-rail{right:22px!important;gap:10px!important;padding:0!important;background:transparent!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;border-radius:0!important;box-shadow:none!important}
    .dots.chapter-rail a{position:relative!important;width:7px!important;height:7px!important;border-radius:999px!important;background:rgba(17,18,23,.16)!important;overflow:visible!important;transition:transform .28s ease,background .28s ease,opacity .28s ease!important}
    .dots.chapter-rail a span,.dots.chapter-rail a em{display:none!important}
    .dots.chapter-rail a.on{height:7px!important;background:#111217!important;transform:scale(1.35)!important}

    .founder-story{
      position:relative;
      min-height:100svh;
      display:grid;
      place-items:center;
      padding:110px 24px 130px;
      background:#fff;
      overflow:hidden;
    }
    .founder-story img{
      display:block;
      width:min(900px,92vw);
      max-height:88svh;
      height:auto;
      object-fit:contain;
    }

    .pricing{position:relative!important;display:block!important;overflow:hidden!important;padding:150px max(24px,8vw) 180px!important;text-align:center!important;background:#fff!important}
    .pricing>h2{position:relative!important;inset:auto!important;display:block!important;width:min(900px,100%)!important;max-width:900px!important;margin:0 auto!important;padding:0!important;transform:none!important;translate:none!important;filter:none!important;white-space:normal!important}
    .pricing>h2.reveal.in{transform:none!important;translate:none!important}
    .pricing>p{position:relative!important;inset:auto!important;display:block!important;width:min(610px,100%)!important;max-width:610px!important;margin:30px auto 0!important;padding:0!important;font-size:16px!important;text-align:center!important;transform:none!important;translate:none!important;white-space:normal!important;color:#7b7e87!important}
    .pricing>p.reveal.in{transform:none!important;translate:none!important}
    .billing-switch{position:relative!important;inset:auto!important;width:max-content!important;max-width:100%!important;margin:34px auto 54px!important;padding:4px!important;display:flex!important;align-items:center!important;gap:4px!important;border:1px solid rgba(17,18,23,.08)!important;border-radius:999px!important;background:rgba(247,247,248,.94)!important;box-shadow:none!important;transform:none!important;translate:none!important;z-index:2!important}
    .billing-switch button{border:0;background:transparent;color:#858890;border-radius:999px;padding:11px 18px;font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .25s ease,color .25s ease;white-space:nowrap}
    .billing-switch button.active{background:#111217;color:#fff;box-shadow:none}
    .billing-switch .save{margin-left:7px;color:#7186c7;font-size:9px;font-weight:650;letter-spacing:.09em;text-transform:uppercase;align-self:center;padding-right:9px;white-space:nowrap}
    .pricing .plans{position:relative!important;z-index:1!important;display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;align-items:stretch!important;gap:16px!important;width:min(1120px,100%)!important;max-width:1120px!important;margin:0 auto!important;padding:0!important;overflow:visible!important;transform:none!important;translate:none!important}
    .pricing .plan{position:relative!important;overflow:hidden!important;transform:none!important;translate:none!important;clip-path:none!important;min-height:450px!important;border-radius:26px!important;padding:30px!important}
    .pricing .plan.reveal,.pricing .plan.reveal.in{transform:none!important;translate:none!important;filter:none!important}
    .pricing .plan::before{display:none!important}
    .pricing .plan-badge{position:static!important;display:inline-flex!important;margin:-8px 0 18px!important;transform:none!important;translate:none!important}
    .pricing .plan h3{margin-top:0!important;font-weight:600!important;letter-spacing:-.025em!important}
    .pricing .plan li{font-size:15px!important;line-height:1.45!important;letter-spacing:-.012em!important}
    .price{font-weight:500!important;letter-spacing:-.055em!important}
    .price small{font-family:var(--font)!important;font-weight:400!important;letter-spacing:-.01em!important}
    .price .annual-note{display:block;margin-top:7px;font-family:var(--font)!important;font-size:11px;font-weight:400;letter-spacing:0;color:#8b8e96}

    @media(max-width:900px){
      .pricing{padding:120px 24px 150px!important}
      .pricing .plans{grid-template-columns:1fr!important;max-width:560px!important}
      .pricing .plan{min-height:0!important}
      .founder-story{min-height:auto;padding:90px 20px 110px}
    }
    @media(max-width:680px){
      .dots.chapter-rail{display:none!important}
      .founder-story{padding:72px 10px 90px}.founder-story img{width:100%;max-height:none}
      .pricing{padding:96px 20px 125px!important}
      .pricing>p{margin-top:24px!important;font-size:14px!important}
      .billing-switch{margin:28px auto 42px!important}
      .billing-switch .save{display:none!important}
    }
  `;
  document.head.appendChild(style);

  const rail=document.querySelector('.dots');
  if(rail){
    rail.classList.add('chapter-rail');
    rail.setAttribute('aria-label','Progress');
    [...rail.querySelectorAll('a')].forEach((link,index)=>{
      link.textContent='';
      link.setAttribute('aria-label',['Local','Styles','Context','Voice'][index]||`Section ${index+1}`);
    });
  }

  const words=['DICTATE','WRITE','REPLY','REWRITE','SUMMARIZE','TRANSLATE','WINDOWS','LOCAL','PRIVATE','CONTEXT','STYLE','CONTROL'];
  document.querySelectorAll('.words span').forEach((el,i)=>{if(words[i]) el.textContent=words[i]});
  const introWords=['DICTATE','UNDERSTAND','REWRITE','WRITE'];
  document.querySelectorAll('.intro-word').forEach((el,i)=>{if(introWords[i]) el.textContent=introWords[i]});

  document.querySelectorAll('.founder-story').forEach(el=>el.remove());
  const pricing=document.querySelector('.pricing');
  if(pricing){
    const section=document.createElement('section');
    section.className='founder-story';
    section.setAttribute('aria-label','Founder note');
    const img=document.createElement('img');
    img.src='/sasha-founder.svg?v=5';
    img.alt='Dotted portrait of Sasha, founder of Nova, with a short personal note.';
    img.loading='eager';
    img.decoding='async';
    section.appendChild(img);
    pricing.before(section);
  }

  const pricingCopy={
    title:['Free','Nova Pro','Nova Ultra'],
    features:[
      ['Unlimited local dictation','90+ languages','3 essential Styles','10 rewrites per day'],
      ['Unlimited dictation and rewriting','All Styles','Automatic app detection','Local processing on your PC','14 days free, no card required'],
      ['Everything in Nova Pro','Context awareness','Custom Styles','Optional Nova Turbo','Full personalization']
    ],
    buttons:['Download','Try Pro','Get Ultra'],
    popular:'Most popular',monthly:'Monthly',annual:'Annual',save:'2 months free',month:'/ month',year:'/ year',billed:'billed annually'
  };

  let billing='monthly';
  let sw=pricing?.querySelector('.billing-switch');
  if(pricing&&!sw){
    sw=document.createElement('div');
    sw.className='billing-switch';
    sw.setAttribute('aria-label','Billing period');
    sw.innerHTML='<button type="button" class="active" data-billing="monthly">Monthly</button><button type="button" data-billing="annual">Annual</button><span class="save">2 months free</span>';
    pricing.querySelector('.plans')?.before(sw);
    sw.querySelectorAll('button').forEach(btn=>btn.addEventListener('click',()=>{
      billing=btn.dataset.billing;
      sw.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===btn));
      renderPricing();
    }));
  }

  function renderPricing(){
    const plans=[...document.querySelectorAll('.pricing .plan')];
    const monthly=[0,4.99,14.99];
    const annual=[0,49.90,149.90];
    plans.forEach((plan,i)=>{
      const h3=plan.querySelector('h3'); if(h3) h3.textContent=pricingCopy.title[i];
      let badge=plan.querySelector('.plan-badge');
      if(i===1){
        if(!badge){badge=document.createElement('span');badge.className='plan-badge';plan.prepend(badge)}
        badge.textContent=pricingCopy.popular;
      }else if(badge){badge.remove()}
      const price=plan.querySelector('.price');
      if(price){
        if(i===0) price.innerHTML='0 €';
        else if(billing==='monthly') price.innerHTML=`${monthly[i].toFixed(2)} € <small>${pricingCopy.month}</small>`;
        else price.innerHTML=`${annual[i].toFixed(2)} € <small>${pricingCopy.year}</small><span class="annual-note">${pricingCopy.billed}</span>`;
      }
      const ul=plan.querySelector('ul');
      if(ul) ul.innerHTML=pricingCopy.features[i].map(x=>`<li>${x}</li>`).join('');
      const btn=plan.querySelector('.black-btn'); if(btn) btn.textContent=pricingCopy.buttons[i];
    });
  }

  renderPricing();
})();
