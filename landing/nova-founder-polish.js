(()=>{
  // La page déclare sa langue dans <html lang> : on la respecte au lieu de la
  // forcer. L'accueil anglaise déclare lang="en" et retrouve donc exactement le
  // comportement d'avant ; l'accueil française déclare lang="fr" et le garde.
  const isFr=document.documentElement.lang==='fr';
  if(!isFr){
    document.documentElement.lang='en';
    document.body.classList.add('english');
  }
  const T=isFr?{
    legal:'Mentions légales et confidentialité',
    progress:'Progression',
    rail:['Local','Styles','Contexte','Voix'],
    words:['DICTER','ÉCRIRE','RÉPONDRE','REFORMULER','RÉSUMER','TRADUIRE','WINDOWS','LOCAL','PRIVÉ','CONTEXTE','STYLE','CONTRÔLE'],
    intro:['DICTER','COMPRENDRE','REFORMULER','ÉCRIRE'],
    founderAlt:'Portrait pointilliste de Sasha, fondateur de Nova, accompagné d’une courte note personnelle.',
    founderNote:'Note du fondateur'
  }:{
    legal:'Legal, Terms & Privacy',
    progress:'Progress',
    rail:['Local','Styles','Context','Voice'],
    words:['DICTATE','WRITE','REPLY','REWRITE','SUMMARIZE','TRANSLATE','WINDOWS','LOCAL','PRIVATE','CONTEXT','STYLE','CONTROL'],
    intro:['DICTATE','UNDERSTAND','REWRITE','WRITE'],
    founderAlt:'Dotted portrait of Sasha, founder of Nova, with a short personal note.',
    founderNote:'Founder note'
  };

  const legacyLang=document.getElementById('langBtn');
  if(legacyLang) legacyLang.remove();

  const dock=document.querySelector('.dock');
  if(dock&&!dock.querySelector('.legal-link')){
    const legal=document.createElement('a');
    legal.className='circle legal-link';
    legal.href='/legal.html';
    legal.setAttribute('aria-label',T.legal);
    legal.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5M10 12h6M10 16h6"/></svg>';
    dock.appendChild(legal);
  }

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

    h1,h2,h3,strong,.price{font-family:var(--display)!important;color:#111217}
    .manifesto h1,.chapter h2,.usecases h2,.pricing>h2,.faq>h2,.final h2{
      font-weight:500!important;letter-spacing:-.065em!important;line-height:.92!important;text-wrap:balance;
    }
    .manifesto h1{font-size:clamp(48px,7.2vw,108px)!important}
    .chapter h2{font-size:clamp(48px,6.7vw,98px)!important}
    .usecases h2,.pricing>h2,.faq>h2{font-size:clamp(48px,7vw,100px)!important}
    .final h2{font-size:clamp(60px,9vw,132px)!important}
    .manifesto p,.chapter p,.usecases p,.pricing>p,.faq-item p{font-weight:400!important;letter-spacing:-.018em!important;line-height:1.55!important}
    .chapter-label,.hero-note,.words span,.cinema-copy small,.num,.plan-badge,.plan-tier{font-weight:600!important;letter-spacing:.16em!important;text-transform:uppercase!important}
    .words span{font-size:clamp(10px,.85vw,12px)!important}
    .black-btn,.dock .main,.enter{font-weight:600!important;letter-spacing:-.015em!important}

    .cinema{background:radial-gradient(circle at 13% 39%,rgba(104,145,181,.91) 0,rgba(151,188,216,.87) 22%,transparent 49%),radial-gradient(circle at 81% 27%,rgba(247,227,183,.93) 0,rgba(235,216,180,.84) 23%,transparent 49%),radial-gradient(circle at 63% 82%,rgba(183,222,202,.92) 0,rgba(183,222,202,.78) 25%,transparent 54%),linear-gradient(132deg,#bed3e0 0,#dfe9e8 42%,#eee4c9 68%,#c8e1d4 100%)!important}

    .dots.chapter-rail{right:22px!important;gap:10px!important;padding:0!important;background:transparent!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;border-radius:0!important;box-shadow:none!important}
    .dots.chapter-rail a{position:relative!important;width:7px!important;height:7px!important;border-radius:999px!important;background:rgba(17,18,23,.16)!important;overflow:visible!important;transition:transform .28s ease,background .28s ease,opacity .28s ease!important}
    .dots.chapter-rail a span,.dots.chapter-rail a em{display:none!important}
    .dots.chapter-rail a.on{height:7px!important;background:#111217!important;transform:scale(1.35)!important}

    /* Symmetrical dock: the main Download button is now exactly centered in the viewport. */
    .dock{display:grid!important;grid-template-columns:58px 58px 236px 58px 58px!important;align-items:center!important;gap:8px!important;width:max-content!important;max-width:calc(100vw - 24px)!important}
    .dock a,.dock button{width:58px!important;height:58px!important}
    .dock .main{width:236px!important;min-width:236px!important;padding:0 22px!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:9px!important;white-space:nowrap!important}
    .dock .legal-link{position:relative}
    .dock .legal-link::after{content:"Legal";position:absolute;left:50%;bottom:calc(100% + 9px);transform:translate(-50%,5px);padding:6px 9px;border-radius:999px;background:#111217;color:#fff;font-size:9px;font-weight:600;letter-spacing:.01em;opacity:0;pointer-events:none;transition:opacity .2s ease,transform .2s ease}
    .dock .legal-link:hover::after{opacity:1;transform:translate(-50%,0)}

    /* Chapter CTAs share the same optical center and width as Download Nova. */
    .chapter .black-btn{width:236px!important;max-width:100%!important;min-height:52px!important;margin-left:auto!important;margin-right:auto!important;align-self:center!important;display:flex!important;align-items:center!important;justify-content:center!important;text-align:center!important}

    /* Founder portrait: same compact editorial composition as the reference, using Sasha's dotted portrait. */
    .founder-story{position:relative;min-height:auto;display:grid;place-items:center;padding:118px 24px 132px;background:#fff;overflow:hidden}
    .founder-story img{display:block;width:min(720px,88vw);height:auto;max-height:none;object-fit:contain}

    /* Pricing becomes a clear value ladder instead of three visually equivalent cards. */
    .pricing{position:relative!important;display:block!important;overflow:hidden!important;padding:145px max(24px,7vw) 185px!important;text-align:center!important;background:#fff!important}
    .pricing>h2{position:relative!important;display:block!important;width:min(980px,100%)!important;max-width:980px!important;margin:0 auto!important;padding:0!important;transform:none!important;translate:none!important;filter:none!important;white-space:normal!important}
    .pricing>h2.reveal.in{transform:none!important;translate:none!important}
    .pricing>p{position:relative!important;display:block!important;width:min(650px,100%)!important;max-width:650px!important;margin:28px auto 0!important;padding:0!important;font-size:16px!important;line-height:1.6!important;text-align:center!important;transform:none!important;translate:none!important;color:#757983!important}
    .pricing>p.reveal.in{transform:none!important;translate:none!important}

    .billing-switch{position:relative!important;width:max-content!important;max-width:100%!important;margin:36px auto 58px!important;padding:4px!important;display:flex!important;align-items:center!important;gap:4px!important;border:1px solid rgba(17,18,23,.08)!important;border-radius:999px!important;background:rgba(247,247,248,.96)!important;box-shadow:0 12px 38px rgba(46,53,76,.05)!important;transform:none!important;translate:none!important;z-index:3!important}
    .billing-switch button{border:0;background:transparent;color:#858890;border-radius:999px;padding:11px 19px;font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .22s ease,color .22s ease;white-space:nowrap}
    .billing-switch button.active{background:#111217;color:#fff;box-shadow:none}
    .billing-switch .save{margin-left:7px;color:#6f83c4;font-size:9px;font-weight:650;letter-spacing:.09em;text-transform:uppercase;padding-right:10px;white-space:nowrap}

    .pricing .plans{position:relative!important;z-index:1!important;display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;align-items:stretch!important;gap:18px!important;width:min(1180px,100%)!important;max-width:1180px!important;margin:0 auto!important;padding:0!important;overflow:visible!important;transform:none!important;translate:none!important}
    .pricing .plan{position:relative!important;overflow:hidden!important;display:flex!important;flex-direction:column!important;transform:none!important;translate:none!important;clip-path:none!important;min-height:590px!important;border-radius:30px!important;padding:32px!important;background:rgba(255,255,255,.9)!important;border:1px solid rgba(17,18,23,.075)!important;box-shadow:0 24px 74px rgba(64,73,108,.07)!important;text-align:left!important}
    .pricing .plan.reveal,.pricing .plan.reveal.in{transform:none!important;translate:none!important;filter:none!important}
    .pricing .plan::before{display:none!important}
    .pricing .plan::after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(420px circle at 50% 0%,rgba(174,191,236,.08),transparent 62%);opacity:.65}
    .pricing .plan.featured{background:linear-gradient(150deg,#eef3fd 0%,#f6f1fb 58%,#fff 100%)!important;border-color:rgba(126,150,220,.25)!important;box-shadow:0 32px 95px rgba(96,112,170,.16)!important}
    .pricing .plan>*{position:relative;z-index:1}
    .pricing .plan-badge{display:inline-flex!important;align-self:flex-start!important;margin:0 0 15px!important;padding:7px 10px!important;border-radius:999px!important;background:rgba(111,131,196,.11)!important;color:#6379bd!important;font-size:9px!important;line-height:1!important;transform:none!important;translate:none!important}
    .plan-tier{display:block;margin-bottom:17px;color:#a0a3aa;font-size:9px;line-height:1.2}
    .pricing .plan h3{margin:0!important;font-size:17px!important;font-weight:600!important;letter-spacing:-.03em!important;display:flex!important;align-items:center!important;gap:8px!important}
    .tier-badge{display:inline-flex!important;align-items:center!important;padding:3px 9px!important;border-radius:999px!important;font-size:9px!important;font-weight:700!important;letter-spacing:.08em!important;text-transform:uppercase!important;line-height:1.6!important;white-space:nowrap!important}
    .tier-badge.pro{background:linear-gradient(135deg,#7FB6FF 0%,#0A84FF 45%,#0060DF 100%)!important;color:#fff!important;box-shadow:0 2px 10px rgba(10,132,255,.35)!important}
    .tier-badge.ultra{background:linear-gradient(135deg,#D9C8F7 0%,#C9B6F0 45%,#9F86D9 100%)!important;color:#1F1F22!important;box-shadow:0 2px 10px rgba(159,134,217,.35)!important}
    .price{margin:23px 0 10px!important;font-size:54px!important;font-weight:500!important;letter-spacing:-.06em!important;line-height:1!important}
    .price small{font-size:12px!important;font-weight:400!important;letter-spacing:-.01em!important;color:#858891!important}
    .price .annual-note{display:block;margin-top:9px;font-size:11px;font-weight:400;letter-spacing:0;color:#8b8e96}
    .plan-kicker{min-height:48px;margin:0 0 25px;color:#6f737d;font-size:13px;line-height:1.55;letter-spacing:-.01em}
    .pricing .plan ul{list-style:none!important;display:grid!important;gap:13px!important;margin:0!important;padding:0!important;color:#676b75!important;font-size:14px!important;line-height:1.45!important;flex:0 0 auto!important}
    .pricing .plan li{position:relative;padding-left:25px!important}
    .pricing .plan li::before{content:"✓"!important;position:absolute;left:0;top:0;color:#8198dc!important;font-weight:700!important;margin:0!important}
    .pricing .plan li.limited{color:#92959d!important}
    .pricing .plan li.limited::before{content:"·"!important;color:#b0b2b8!important;font-size:18px!important;line-height:.8!important}
    .limit-tag{display:inline-flex;margin-left:7px;padding:3px 5px;border-radius:999px;background:#f3f3f4;color:#94969c;font-size:8px;font-weight:650;letter-spacing:.06em;text-transform:uppercase;vertical-align:2px}
    .limit-tag-new{background:linear-gradient(135deg,#D9C8F7 0%,#C9B6F0 45%,#9F86D9 100%)!important;color:#1F1F22!important;box-shadow:0 1px 6px rgba(159,134,217,.35)!important}

    .upgrade-preview{margin-top:25px;padding:16px 0 0;border-top:1px solid rgba(17,18,23,.07);display:grid;gap:9px}
    .upgrade-preview-title{font-size:9px;font-weight:650;letter-spacing:.12em;text-transform:uppercase;color:#a0a3aa}
    .upgrade-row{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:#777b84}
    .upgrade-row span:last-child{flex:none;padding:4px 7px;border-radius:999px;background:#f1f2f5;color:#70747d;font-size:8px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
    .upgrade-tag.pro{background:rgba(10,132,255,.12)!important;color:#0A66D0!important}
    .upgrade-tag.ultra{background:rgba(159,134,217,.16)!important;color:#7C5FBF!important}
    .upgrade-preview.unlocked{padding:15px 16px;border:1px solid rgba(126,150,220,.13);border-radius:16px;background:rgba(255,255,255,.48)}
    .upgrade-preview.unlocked .upgrade-preview-title{color:#667bc0}
    .upgrade-preview.unlocked p{margin:0;color:#646975;font-size:12px;line-height:1.45}

    .pricing .plan .black-btn{width:100%!important;min-height:58px!important;margin-top:auto!important;padding:0 18px!important;display:flex!important;align-items:center!important;justify-content:center!important;border-radius:999px!important;text-align:center!important;font-size:13px!important}
    .plan-foot{margin-top:12px;text-align:center;color:#a0a2a8;font-size:10px;line-height:1.4}
    .featured .black-btn{box-shadow:0 14px 30px rgba(17,18,23,.14)!important}

    @media(max-width:900px){
      .pricing{padding:118px 24px 150px!important}
      .pricing .plans{grid-template-columns:1fr!important;max-width:590px!important}
      .pricing .plan{min-height:0!important}
      .founder-story{padding:96px 20px 110px}
    }
    @media(max-width:680px){
      .dots.chapter-rail{display:none!important}
      .founder-story{padding:70px 12px 84px}.founder-story img{width:min(620px,100%)}
      .pricing{padding:94px 18px 118px!important}
      .pricing>p{margin-top:23px!important;font-size:14px!important}
      .billing-switch{margin:28px auto 42px!important}
      .billing-switch .save{display:none!important}
      .pricing .plan{padding:26px!important;border-radius:25px!important}

      /* Mobile keeps the main CTA optically centered: Pricing / Download / Legal. */
      .dock{grid-template-columns:44px minmax(174px,216px) 44px!important;gap:6px!important}
      .dock #soundBtn,.dock a[href="#film"]{display:none!important}
      .dock a[href="#tarifs"]{display:grid!important;grid-column:1!important;grid-row:1!important;width:44px!important;height:44px!important}
      .dock .main{grid-column:2!important;grid-row:1!important;width:100%!important;min-width:0!important;height:44px!important;font-size:11px!important;padding:0 14px!important}
      .dock .legal-link{grid-column:3!important;grid-row:1!important;width:44px!important;height:44px!important}
      .dock .legal-link::after{display:none}
    }
    @media(max-width:430px){.dock{grid-template-columns:42px minmax(160px,190px) 42px!important}.dock a[href="#tarifs"],.dock .legal-link{width:42px!important;height:42px!important}.dock .main{height:42px!important}}
  `;
  document.head.appendChild(style);

  const rail=document.querySelector('.dots');
  if(rail){
    rail.classList.add('chapter-rail');
    rail.setAttribute('aria-label',T.progress);
    [...rail.querySelectorAll('a')].forEach((link,index)=>{
      link.textContent='';
      link.setAttribute('aria-label',T.rail[index]||`Section ${index+1}`);
    });
  }

  const words=T.words;
  document.querySelectorAll('.words span').forEach((el,i)=>{if(words[i]) el.textContent=words[i]});
  const introWords=T.intro;
  document.querySelectorAll('.intro-word').forEach((el,i)=>{if(introWords[i]) el.textContent=introWords[i]});

  document.querySelectorAll('.founder-story').forEach(el=>el.remove());
  const pricing=document.querySelector('.pricing');
  const audienceMode=pricing?.classList.contains('audiences');
  if(pricing){
    const section=document.createElement('section');
    section.className='founder-story';
    section.setAttribute('aria-label',T.founderNote);
    const img=document.createElement('img');
    img.src='/sasha-founder.svg?v=8';
    img.alt=T.founderAlt;
    img.loading='eager';
    img.decoding='async';
    section.appendChild(img);
    pricing.before(section);

    if(!audienceMode){
      const heading=pricing.querySelector(':scope > h2');
      const intro=pricing.querySelector(':scope > p');
      if(heading) heading.innerHTML='Start free.<br>Unlock the full Nova.';
      if(intro) intro.textContent='Free covers the essentials. Pro removes every local limit and adds true personalization — vocabulary, variables, shortcuts, all yours. Ultra brings Nova’s full intelligence: unlimited Turbo, automatic meeting notes and real context awareness.';
    }
  }

  if(audienceMode)return;

  const pricingCopy={
    title:['Free','Nova Pro','Nova Ultra'],
    tier:['START HERE','UNLIMITED & PERSONAL','FULL INTELLIGENCE'],
    kicker:[
      'Try Nova locally, plus 20 free Turbo rewrites to see what cloud speed feels like.',
      'Every local limit removed, plus the personalization layer that makes Nova sound like you — vocabulary, variables, shortcuts.',
      'Nova’s complete intelligence: unlimited Turbo, meetings turned into notes automatically, and full context on everything you write.'
    ],
    features:[
      [
        {label:'Unlimited local dictation'},
        {label:'90+ languages'},
        {label:'3 essential Styles',limited:true,tag:'Free'},
        {label:'20 free Turbo rewrites, once',limited:true,tag:'One-time'}
      ],
      [
        {label:'Unlimited dictation and rewriting'},
        {label:'All Styles, including Automatic',tag:'New'},
        {label:'Personalized vocabulary & glossary',tag:'New'},
        {label:'Smart variables & templates',tag:'New'},
        {label:'Custom keyboard shortcuts',tag:'New'},
        {label:'Unlimited history + export'},
        {label:'Adaptive performance profiles'},
        {label:'Priority support'}
      ],
      [
        {label:'Everything in Nova Pro'},
        {label:'Nova Turbo, unlimited',tag:'New'},
        {label:'Meeting mode — auto notes',tag:'New'},
        {label:'Context awareness',tag:'New'},
        {label:'Build your own Styles',tag:'New'},
        {label:'Nova Apex — maximum power'},
        {label:'Priority support, direct line'}
      ]
    ],
    buttons:['Download Free','Start 7-day Pro trial','Get Nova Ultra'],
    foot:['No card required','No card required','For advanced workflows'],
    popular:'Most popular',monthly:'Monthly',annual:'Annual',save:'2 months free',month:'/ month',year:'/ year',billed:'2 months free · billed annually'
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

  function addUpgradePreview(plan,index){
    plan.querySelectorAll('.upgrade-preview').forEach(el=>el.remove());
    const box=document.createElement('div');
    if(index===0){
      box.className='upgrade-preview';
      box.innerHTML='<span class="upgrade-preview-title">Unlock with Pro</span><div class="upgrade-row"><span>All Styles, unlimited</span><span class="upgrade-tag pro">Pro</span></div><div class="upgrade-row"><span>Personalized vocabulary</span><span class="upgrade-tag pro">Pro</span></div>';
    }else if(index===1){
      box.className='upgrade-preview';
      box.innerHTML='<span class="upgrade-preview-title">Unlock with Ultra</span><div class="upgrade-row"><span>Nova Turbo, unlimited</span><span class="upgrade-tag ultra">Ultra</span></div><div class="upgrade-row"><span>Meeting mode — auto notes</span><span class="upgrade-tag ultra">Ultra</span></div>';
    }else{
      box.className='upgrade-preview unlocked';
      box.innerHTML='<span class="upgrade-preview-title">Everything unlocked</span><p>Unlimited Turbo, meeting mode, context awareness, custom Styles — Nova’s full intelligence.</p>';
    }
    const button=plan.querySelector('.black-btn');
    if(button) plan.insertBefore(box,button); else plan.appendChild(box);
  }

  function renderPricing(){
    const plans=[...document.querySelectorAll('.pricing .plan')];
    const monthly=[0,4.99,14.99];
    const annual=[0,49.90,149.90];
    plans.forEach((plan,i)=>{
      plan.querySelectorAll('.plan-badge,.plan-tier,.plan-kicker,.plan-foot').forEach(el=>el.remove());

      const h3=plan.querySelector('h3');
      if(h3){
        h3.innerHTML='';
        h3.appendChild(document.createTextNode(pricingCopy.title[i]));
        if(i===1||i===2){
          const tierBadge=document.createElement('span');
          tierBadge.className=i===1?'tier-badge pro':'tier-badge ultra';
          tierBadge.textContent=i===1?'Pro':'Ultra';
          h3.appendChild(tierBadge);
        }
        const tier=document.createElement('span');
        tier.className='plan-tier';
        tier.textContent=pricingCopy.tier[i];
        h3.before(tier);
        if(i===1){
          const badge=document.createElement('span');
          badge.className='plan-badge';
          badge.textContent=pricingCopy.popular;
          tier.before(badge);
        }
      }

      const price=plan.querySelector('.price');
      if(price){
        if(i===0) price.innerHTML='0 €';
        else if(billing==='monthly') price.innerHTML=`${monthly[i].toFixed(2)} € <small>${pricingCopy.month}</small>`;
        else price.innerHTML=`${annual[i].toFixed(2)} € <small>${pricingCopy.year}</small><span class="annual-note">${pricingCopy.billed}</span>`;
        const kicker=document.createElement('p');
        kicker.className='plan-kicker';
        kicker.textContent=pricingCopy.kicker[i];
        price.after(kicker);
      }

      const ul=plan.querySelector('ul');
      if(ul){
        ul.innerHTML='';
        pricingCopy.features[i].forEach(feature=>{
          const li=document.createElement('li');
          if(feature.limited) li.className='limited';
          li.append(document.createTextNode(feature.label));
          if(feature.tag){
            const tag=document.createElement('span');
            tag.className=feature.tag==='New'?'limit-tag limit-tag-new':'limit-tag';
            tag.textContent=feature.tag;
            li.appendChild(tag);
          }
          ul.appendChild(li);
        });
      }

      const btn=plan.querySelector('.black-btn');
      if(btn) btn.textContent=pricingCopy.buttons[i];
      addUpgradePreview(plan,i);

      const foot=document.createElement('div');
      foot.className='plan-foot';
      foot.textContent=pricingCopy.foot[i];
      plan.appendChild(foot);
    });
  }

  renderPricing();
})();
