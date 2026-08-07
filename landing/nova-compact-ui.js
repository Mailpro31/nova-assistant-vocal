(()=>{
  const style=document.createElement('style');
  style.textContent=`
    /* Compact, optically centered controls. */
    .dock.dock-compact{
      display:grid!important;
      grid-template-columns:46px 188px 46px!important;
      align-items:center!important;
      gap:7px!important;
      width:max-content!important;
      max-width:calc(100vw - 22px)!important;
      filter:drop-shadow(0 12px 24px rgba(43,49,71,.12))!important;
      transition:transform .35s ease,opacity .25s ease!important;
    }
    .dock.dock-compact a,.dock.dock-compact button{
      width:46px!important;
      height:46px!important;
    }
    .dock.dock-compact #soundBtn{grid-column:1!important;display:grid!important;place-items:center!important}
    .dock.dock-compact .main{
      grid-column:2!important;
      width:188px!important;
      min-width:188px!important;
      height:46px!important;
      padding:0 18px!important;
      font-size:11px!important;
      display:grid!important;
      place-items:center!important;
      transform:none!important;
    }
    .dock.dock-compact .legal-link{
      grid-column:3!important;
      width:46px!important;
      height:46px!important;
    }
    .dock.dock-compact svg{width:15px!important;height:15px!important}
    .dock.dock-compact a:hover,.dock.dock-compact button:hover{transform:translateY(-2px)!important}

    /* No floating dock over pricing CTAs. */
    body.pricing-focus .dock{opacity:0!important;pointer-events:none!important;transform:translate(-50%,10px)!important}

    /* Chapter buttons return to the smaller Tekiyo-like proportion. */
    .chapter .black-btn{
      width:180px!important;
      min-width:0!important;
      max-width:100%!important;
      min-height:44px!important;
      height:44px!important;
      padding:0 17px!important;
      margin-left:auto!important;
      margin-right:auto!important;
      align-self:center!important;
      font-size:11px!important;
      border-radius:999px!important;
      display:flex!important;
      align-items:center!important;
      justify-content:center!important;
      text-align:center!important;
    }

    /* Pricing: tighter cards, smaller CTAs, guaranteed spacing. */
    .pricing .plans{gap:16px!important;max-width:1120px!important}
    .pricing .plan{
      min-height:548px!important;
      padding:28px!important;
      border-radius:26px!important;
    }
    .pricing .plan-badge{margin-bottom:12px!important;padding:6px 9px!important}
    .plan-tier{margin-bottom:14px!important}
    .price{font-size:49px!important;margin:20px 0 9px!important}
    .plan-kicker{min-height:42px!important;margin-bottom:20px!important;font-size:12px!important}
    .pricing .plan ul{gap:11px!important;font-size:13px!important}
    .upgrade-preview{
      margin-top:20px!important;
      margin-bottom:17px!important;
      padding-top:14px!important;
      gap:8px!important;
    }
    .upgrade-preview.unlocked{padding:13px 14px!important}
    .pricing .plan .black-btn{
      width:100%!important;
      min-height:46px!important;
      height:46px!important;
      padding:0 16px!important;
      margin-top:auto!important;
      font-size:11px!important;
      border-radius:999px!important;
    }
    .plan-foot{margin-top:10px!important;font-size:9px!important}
    .billing-switch{margin:32px auto 48px!important;transform:scale(.94)!important}

    /* Nova Voice — always-visible live speech animation on desktop. */
    .voice-orb .bars{
      position:absolute!important;
      left:50%!important;
      top:50%!important;
      transform:translate(-50%,-50%)!important;
      display:flex!important;
      align-items:center!important;
      justify-content:center!important;
      gap:8px!important;
      z-index:8!important;
      pointer-events:none!important;
    }
    .voice-orb .bars i{
      display:block!important;
      width:5px!important;
      height:24px!important;
      border-radius:999px!important;
      background:#fff!important;
      opacity:.98!important;
      transform-origin:center!important;
      animation:novaSpeakBar 1.05s ease-in-out infinite!important;
      will-change:transform,opacity!important;
      box-shadow:0 0 10px rgba(255,255,255,.22)!important;
    }
    .voice-orb .bars i:nth-child(1){animation-delay:-.52s!important;--voice-scale:.42}
    .voice-orb .bars i:nth-child(2){animation-delay:-.19s!important;--voice-scale:.82}
    .voice-orb .bars i:nth-child(3){animation-delay:-.71s!important;--voice-scale:1.18}
    .voice-orb .bars i:nth-child(4){animation-delay:-.34s!important;--voice-scale:.68}
    .voice-orb .bars i:nth-child(5){animation-delay:-.61s!important;--voice-scale:1.02}
    .voice-orb>.orb{animation:novaVoiceBreath 2.8s ease-in-out infinite!important}
    @keyframes novaSpeakBar{
      0%,100%{transform:scaleY(.34);opacity:.72}
      22%{transform:scaleY(var(--voice-scale,.8));opacity:1}
      48%{transform:scaleY(.52);opacity:.84}
      72%{transform:scaleY(calc(var(--voice-scale,.8) * 1.12));opacity:1}
    }
    @keyframes novaVoiceBreath{
      0%,100%{transform:scale(1)}
      50%{transform:scale(1.018)}
    }

    @media(max-width:900px){
      .pricing .plan{min-height:0!important}
    }
    @media(max-width:680px){
      .dock.dock-compact{
        grid-template-columns:42px minmax(158px,184px) 42px!important;
        gap:6px!important;
      }
      .dock.dock-compact a,.dock.dock-compact button,
      .dock.dock-compact .legal-link{width:42px!important;height:42px!important}
      .dock.dock-compact .main{width:100%!important;min-width:0!important;height:42px!important;font-size:10.5px!important}
      .chapter .black-btn{width:168px!important;height:42px!important;min-height:42px!important}
      .pricing .plan{padding:24px!important}
      .pricing .plan .black-btn{height:44px!important;min-height:44px!important}
    }
  `;
  document.head.appendChild(style);

  let attempts=0;
  function apply(){
    attempts++;
    const dock=document.querySelector('.dock');
    if(dock){
      dock.classList.add('dock-compact');
      /* The old play icon only jumped to the cinematic section and added visual noise. */
      dock.querySelector('a[href="#film"]')?.remove();
      /* Keep the dedicated left pricing shortcut; remove only duplicate pricing links. */
      dock.querySelectorAll('a[href="#tarifs"]:not(#soundBtn)').forEach(link=>link.remove());
    }

    const pricing=document.querySelector('.pricing');
    if(pricing&&!pricing.dataset.compactObserved){
      pricing.dataset.compactObserved='1';
      new IntersectionObserver(([entry])=>{
        document.body.classList.toggle('pricing-focus',entry.isIntersecting);
      },{threshold:.08,rootMargin:'-8% 0px -8%'}).observe(pricing);
    }

    const ready=dock?.querySelector('.legal-link')&&document.querySelector('.pricing .plan .black-btn');
    if(!ready&&attempts<30)setTimeout(apply,100);
  }

  apply();
})();