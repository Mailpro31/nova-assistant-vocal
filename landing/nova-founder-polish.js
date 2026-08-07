(()=>{
  const style=document.createElement('style');
  style.textContent=`
    html,body{scrollbar-width:none!important;-ms-overflow-style:none!important}
    html::-webkit-scrollbar,body::-webkit-scrollbar,*::-webkit-scrollbar{width:0!important;height:0!important;display:none!important}
    body{padding-bottom:0!important}
    .cinema{background:radial-gradient(circle at 13% 39%,rgba(104,145,181,.91) 0,rgba(151,188,216,.87) 22%,transparent 49%),radial-gradient(circle at 81% 27%,rgba(247,227,183,.93) 0,rgba(235,216,180,.84) 23%,transparent 49%),radial-gradient(circle at 63% 82%,rgba(183,222,202,.92) 0,rgba(183,222,202,.78) 25%,transparent 54%),linear-gradient(132deg,#bed3e0 0,#dfe9e8 42%,#eee4c9 68%,#c8e1d4 100%)!important}
    .dots.chapter-rail{right:22px!important;gap:9px!important;padding:0!important;background:transparent!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;border-radius:0!important;box-shadow:none!important}
    .dots.chapter-rail a{position:relative!important;width:8px!important;height:8px!important;border-radius:999px!important;background:rgba(17,18,23,.16)!important;overflow:visible!important;transition:transform .28s ease,background .28s ease,opacity .28s ease!important}
    .dots.chapter-rail a span,.dots.chapter-rail a em{display:none!important}
    .dots.chapter-rail a.on{height:8px!important;background:#111217!important;transform:scale(1.35)!important}

    .founder-story{position:relative;min-height:100svh;display:grid;place-items:center;padding:36px 24px 82px;background:#fff;overflow:hidden}
    .founder-story img{display:block;width:min(1120px,94vw);height:auto;object-fit:contain;mix-blend-mode:multiply}

    /* Pricing layout: force a clean editorial stack and prevent reveal/transform overlap. */
    .pricing{position:relative!important;display:block!important;overflow:hidden!important;padding:150px max(24px,8vw) 180px!important;text-align:center!important;background:#fff!important}
    .pricing>h2{position:relative!important;inset:auto!important;display:block!important;width:min(980px,100%)!important;max-width:980px!important;margin:0 auto!important;padding:0!important;font-size:clamp(54px,7vw,104px)!important;line-height:.92!important;letter-spacing:-.06em!important;transform:none!important;translate:none!important;filter:none!important;white-space:normal!important;overflow-wrap:normal!important}
    .pricing>h2.reveal.in{transform:none!important;translate:none!important}
    .pricing>p{position:relative!important;inset:auto!important;display:block!important;width:min(620px,100%)!important;max-width:620px!important;margin:30px auto 0!important;padding:0!important;font-size:15px!important;line-height:1.65!important;text-align:center!important;transform:none!important;translate:none!important;white-space:normal!important}
    .pricing>p.reveal.in{transform:none!important;translate:none!important}
    .billing-switch{position:relative!important;inset:auto!important;width:max-content!important;max-width:100%!important;margin:34px auto 54px!important;padding:4px!important;display:flex!important;align-items:center!important;gap:4px!important;border:1px solid rgba(17,18,23,.08)!important;border-radius:999px!important;background:rgba(245,246,249,.92)!important;box-shadow:0 8px 28px rgba(61,70,100,.05)!important;transform:none!important;translate:none!important;z-index:2!important}
    .billing-switch button{border:0;background:transparent;color:#7b7f89;border-radius:999px;padding:10px 16px;font:inherit;font-size:12px;font-weight:650;cursor:pointer;transition:background .25s ease,color .25s ease,box-shadow .25s ease;white-space:nowrap}
    .billing-switch button.active{background:#111217;color:#fff;box-shadow:0 7px 18px rgba(17,18,23,.14)}
    .billing-switch .save{margin-left:6px;color:#667bc0;font-size:9px;font-weight:750;letter-spacing:.08em;text-transform:uppercase;align-self:center;padding-right:8px;white-space:nowrap}
    .pricing .plans{position:relative!important;z-index:1!important;display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;align-items:stretch!important;gap:16px!important;width:min(1120px,100%)!important;max-width:1120px!important;margin:0 auto!important;padding:0!important;overflow:visible!important;transform:none!important;translate:none!important}
    .pricing .plan{position:relative!important;overflow:hidden!important;transform:none!important;translate:none!important;clip-path:none!important;min-height:450px!important;border-radius:28px!important;padding:30px!important}
    .pricing .plan.reveal,.pricing .plan.reveal.in{transform:none!important;translate:none!important;filter:none!important}
    .pricing .plan::before{display:none!important}
    .pricing .plan-badge{position:static!important;margin:-8px 0 16px!important;transform:none!important;translate:none!important}
    .pricing .plan h3{margin-top:0!important}
    .price .annual-note{display:block;margin-top:7px;font-size:11px;font-weight:500;letter-spacing:0;color:#8b8e96}

    @media(max-width:900px){
      .pricing{padding:120px 24px 150px!important}
      .pricing>h2{font-size:clamp(48px,10vw,82px)!important}
      .pricing .plans{grid-template-columns:1fr!important;max-width:560px!important}
      .pricing .plan{min-height:0!important}
    }
    @media(max-width:680px){
      .dots.chapter-rail{display:none!important}
      .founder-story{min-height:auto;padding:38px 12px 64px}.founder-story img{width:100%}
      .pricing{padding:96px 20px 125px!important}
      .pricing>h2{font-size:clamp(44px,14vw,66px)!important;line-height:.95!important}
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

  document.body.classList.add('english');
  document.documentElement.lang='en';
  const langBtn=document.getElementById('langBtn');
  if(langBtn)langBtn.firstChild.nodeValue='FR';

  const words={
    en:['DICTATE','WRITE','REPLY','REWRITE','SUMMARIZE','TRANSLATE','WINDOWS','LOCAL','PRIVATE','CONTEXT','STYLE','CONTROL'],
    fr:['DICTER','ÉCRIRE','RÉPONDRE','REFORMULER','RÉSUMER','TRADUIRE','WINDOWS','LOCAL','PRIVÉ','CONTEXTE','STYLE','CONTRÔLE']
  };
  const introWords={en:['DICTATE','UNDERSTAND','REWRITE','WRITE'],fr:['DICTER','COMPRENDRE','REFORMULER','ÉCRIRE']};

  const pricingCopy={
    en:{
      title:['Free','Nova Pro','Nova Ultra'],
      features:[
        ['Unlimited local dictation','90+ languages','3 essential Styles','10 rewrites per day'],
        ['Unlimited dictation and rewriting','All Styles','Automatic app detection','Local processing on your PC','14 days free, no card required'],
        ['Everything in Nova Pro','Context awareness','Custom Styles','Optional Nova Turbo','Full personalization']
      ],
      buttons:['Download','Try Pro','Get Ultra'],popular:'Most popular',monthly:'Monthly',annual:'Annual',save:'2 months free',month:'/ month',year:'/ year',billed:'billed annually'
    },
    fr:{
      title:['Gratuit','Nova Pro','Nova Ultra'],
      features:[
        ['Dictée locale illimitée','90+ langues','3 Styles essentiels','10 reformulations par jour'],
        ['Dictée et reformulation illimitées','Tous les Styles','Détection selon l’application','Traitement local sur votre PC','14 jours offerts sans carte'],
        ['Tout Nova Pro','Lecture de contexte','Styles personnalisés','Nova Turbo optionnel','Personnalisation complète']
      ],
      buttons:['Télécharger','Essayer Pro','Obtenir Ultra'],popular:'Le plus choisi',monthly:'Mensuel',annual:'Annuel',save:'2 mois offerts',month:'/ mois',year:'/ an',billed:'facturé annuellement'
    }
  };

  let billing='monthly';
  function language(){return document.body.classList.contains('english')?'en':'fr'}
  function syncDynamicLanguage(){
    const lang=language();
    document.documentElement.lang=lang;
    document.querySelectorAll('.words span').forEach((el,i)=>{if(words[lang][i])el.textContent=words[lang][i]});
    document.querySelectorAll('.intro-word').forEach((el,i)=>{if(introWords[lang][i])el.textContent=introWords[lang][i]});
    const sw=document.querySelector('.billing-switch');
    if(sw){
      sw.querySelector('[data-billing="monthly"]').textContent=pricingCopy[lang].monthly;
      sw.querySelector('[data-billing="annual"]').textContent=pricingCopy[lang].annual;
      sw.querySelector('.save').textContent=pricingCopy[lang].save;
    }
    renderPricing();
  }

  document.querySelectorAll('.founder-story').forEach(el=>el.remove());
  const pricing=document.querySelector('.pricing');
  if(pricing){
    const section=document.createElement('section');
    section.className='founder-story';
    section.setAttribute('aria-label','Founder note');
    const img=document.createElement('img');
    img.src='/sasha-founder.webp';
    img.alt='Sasha, founder of Nova.';
    img.loading='eager';
    img.decoding='async';
    section.appendChild(img);
    pricing.before(section);

    let sw=pricing.querySelector('.billing-switch');
    if(!sw){
      sw=document.createElement('div');
      sw.className='billing-switch';
      sw.setAttribute('aria-label','Billing period');
      sw.innerHTML='<button type="button" class="active" data-billing="monthly">Monthly</button><button type="button" data-billing="annual">Annual</button><span class="save">2 months free</span>';
      const plans=pricing.querySelector('.plans');
      plans?.before(sw);
      sw.querySelectorAll('button').forEach(btn=>btn.addEventListener('click',()=>{
        billing=btn.dataset.billing;
        sw.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===btn));
        renderPricing();
      }));
    }
  }

  function renderPricing(){
    const lang=language();
    const copy=pricingCopy[lang];
    const plans=[...document.querySelectorAll('.pricing .plan')];
    const monthly=[0,4.99,14.99];
    const annual=[0,49.90,149.90];
    plans.forEach((plan,i)=>{
      const h3=plan.querySelector('h3'); if(h3)h3.textContent=copy.title[i];
      let badge=plan.querySelector('.plan-badge');
      if(i===1){
        if(!badge){badge=document.createElement('span');badge.className='plan-badge';plan.prepend(badge)}
        badge.textContent=copy.popular;
      } else if(badge){badge.remove()}
      const price=plan.querySelector('.price');
      if(price){
        if(i===0){price.innerHTML='0 €'}
        else if(billing==='monthly') price.innerHTML=`${monthly[i].toFixed(2).replace('.',',')} € <small>${copy.month}</small>`;
        else price.innerHTML=`${annual[i].toFixed(2).replace('.',',')} € <small>${copy.year}</small><span class="annual-note">${copy.billed}</span>`;
      }
      const ul=plan.querySelector('ul');
      if(ul)ul.innerHTML=copy.features[i].map(x=>`<li>${x}</li>`).join('');
      const btn=plan.querySelector('.black-btn'); if(btn)btn.textContent=copy.buttons[i];
    });
  }

  if(langBtn){
    langBtn.addEventListener('click',()=>setTimeout(syncDynamicLanguage,0));
  }
  syncDynamicLanguage();
})();
