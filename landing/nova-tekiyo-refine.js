(()=>{
  const style=document.createElement('style');
  style.textContent=`
    /* Keep the editorial content optically centered at every width. */
    .chapter,.chapter-inner,.manifesto,.manifesto h1,.manifesto p{
      text-align:center!important;
    }
    .chapter-inner{
      width:min(720px,100%)!important;
      margin-left:auto!important;
      margin-right:auto!important;
      justify-items:center!important;
      align-items:center!important;
    }
    .chapter h2,.chapter p,.chapter-label{
      margin-left:auto!important;
      margin-right:auto!important;
      text-align:center!important;
    }
    .chapter p{max-width:520px!important}
    .construct,.style-card,.context-viz,.voice-orb{margin-left:auto!important;margin-right:auto!important}
    .construct .t3{left:50%!important;transform:translateX(-50%)!important}

    /* The section CTAs return to the small Tekiyo-like scale. */
    .chapter .black-btn{
      width:154px!important;
      min-width:154px!important;
      max-width:154px!important;
      min-height:40px!important;
      height:40px!important;
      padding:0 14px!important;
      font-size:10.5px!important;
      line-height:1!important;
      margin-left:auto!important;
      margin-right:auto!important;
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
      border-radius:999px!important;
      box-shadow:0 8px 22px rgba(0,0,0,.11)!important;
    }
    html body #voice .chapter-inner>a.black-btn{
      width:108px!important;
      min-width:108px!important;
      max-width:108px!important;
      height:36px!important;
      min-height:36px!important;
      padding:0 12px!important;
      font-size:10px!important;
      margin:0 auto 58px!important;
    }
    #voice .chapter-inner{padding-bottom:18px!important}

    /* Keep the dock compact and perfectly symmetric around Download Nova. */
    .dock.dock-compact{
      grid-template-columns:42px 176px 42px!important;
      gap:6px!important;
    }
    .dock.dock-compact a,.dock.dock-compact button,
    .dock.dock-compact .legal-link{width:42px!important;height:42px!important}
    .dock.dock-compact .main{
      width:176px!important;
      min-width:176px!important;
      height:42px!important;
      padding:0 15px!important;
      font-size:10.5px!important;
    }
    .dock.dock-compact svg{width:14px!important;height:14px!important}

    /* Manifesto: no rotating/glowing graphics around the inline frame. Only the Nova bubble moves. */
    .manifesto.ambient::before{display:none!important}
    .manifesto{
      min-height:108svh!important;
      padding:145px 24px 175px!important;
      overflow:hidden!important;
    }
    .manifesto h1{
      width:min(1080px,92vw)!important;
      max-width:1080px!important;
      margin:0 auto!important;
      font-size:clamp(44px,6.45vw,96px)!important;
      line-height:.96!important;
    }
    .manifesto p{
      width:min(520px,86vw)!important;
      left:50%!important;
      transform:translateX(-50%)!important;
    }
    .inline-shot{
      background:#f2f4f9!important;
      border:1px solid rgba(17,18,23,.055)!important;
      box-shadow:0 12px 34px rgba(58,68,101,.08)!important;
      isolation:isolate!important;
    }
    .inline-shot::before{display:none!important}
    .inline-shot .orb{
      width:34%!important;
      animation:novaBubbleMove 5.2s cubic-bezier(.45,0,.55,1) infinite!important;
      will-change:transform!important;
    }
    @keyframes novaBubbleMove{
      0%,100%{transform:translate3d(-8px,3px,0)}
      28%{transform:translate3d(8px,-5px,0)}
      55%{transform:translate3d(5px,6px,0)}
      78%{transform:translate3d(-6px,-4px,0)}
    }

    /* Cinematic page: restrained Tekiyo-like art direction — one canvas, one moving Nova bubble, two quiet messages. */
    .cinema{min-height:175svh!important;background:#fff!important}
    .cinema-media{
      top:24px!important;
      width:calc(100% - 40px)!important;
      height:calc(100svh - 48px)!important;
      margin:0 20px!important;
      border-radius:30px!important;
      overflow:hidden!important;
      transform:none!important;
      background:
        radial-gradient(circle at 15% 34%,rgba(133,177,211,.72),transparent 37%),
        radial-gradient(circle at 82% 30%,rgba(242,218,166,.78),transparent 38%),
        radial-gradient(circle at 58% 82%,rgba(191,222,205,.68),transparent 39%),
        linear-gradient(135deg,#dceaf1 0%,#eef1e9 48%,#f1dfb8 100%)!important;
      box-shadow:inset 0 0 0 1px rgba(255,255,255,.42)!important;
    }
    .cinema-media::before{
      content:""!important;
      display:block!important;
      position:absolute!important;
      width:min(560px,54vw)!important;
      height:min(560px,54vw)!important;
      left:50%!important;
      top:48%!important;
      inset:auto!important;
      transform:translate(-50%,-50%)!important;
      border-radius:50%!important;
      background:radial-gradient(circle,rgba(255,255,255,.54) 0 12%,rgba(255,255,255,.18) 34%,transparent 68%)!important;
      filter:blur(18px)!important;
      opacity:.85!important;
      animation:none!important;
    }
    .cinema-media::after{
      background:linear-gradient(180deg,rgba(255,255,255,.58),transparent 12%,transparent 82%,rgba(255,255,255,.46))!important;
    }
    .cinema-shape{display:none!important}
    .cinema-orb{
      width:78px!important;
      height:78px!important;
      left:50%!important;
      right:auto!important;
      top:47%!important;
      transform:translate(-50%,-50%)!important;
      animation:novaCinemaMove 6.2s cubic-bezier(.45,0,.55,1) infinite!important;
      z-index:7!important;
    }
    @keyframes novaCinemaMove{
      0%,100%{transform:translate(-50%,-50%) translate3d(-18px,8px,0)}
      35%{transform:translate(-50%,-50%) translate3d(16px,-12px,0)}
      67%{transform:translate(-50%,-50%) translate3d(10px,13px,0)}
    }
    .cinema-copy{
      height:100svh!important;
      margin-top:-100svh!important;
      transform:none!important;
      opacity:1!important;
    }
    .cinema-copy p{
      max-width:260px!important;
      padding:12px 15px!important;
      border:1px solid rgba(255,255,255,.34)!important;
      border-radius:18px!important;
      background:rgba(255,255,255,.22)!important;
      backdrop-filter:blur(13px)!important;
      -webkit-backdrop-filter:blur(13px)!important;
      color:#fff!important;
      font-size:clamp(17px,1.75vw,25px)!important;
      font-weight:560!important;
      line-height:1.02!important;
      letter-spacing:-.04em!important;
      text-shadow:0 2px 18px rgba(49,58,78,.13)!important;
    }
    .cinema-copy .a{left:8vw!important;top:28vh!important;text-align:left!important}
    .cinema-copy .b{right:8vw!important;top:auto!important;bottom:27vh!important;text-align:right!important}
    .cinema-copy small{bottom:6.5vh!important;color:rgba(17,18,23,.52)!important}

    @media(max-width:680px){
      .chapter .black-btn{width:142px!important;min-width:142px!important;height:38px!important;min-height:38px!important}
      html body #voice .chapter-inner>a.black-btn{width:102px!important;min-width:102px!important;max-width:102px!important;height:34px!important;min-height:34px!important;margin-bottom:52px!important}
      .dock.dock-compact{grid-template-columns:40px minmax(154px,170px) 40px!important}
      .dock.dock-compact a,.dock.dock-compact button,.dock.dock-compact .legal-link{width:40px!important;height:40px!important}
      .dock.dock-compact .main{width:100%!important;min-width:0!important;height:40px!important}
      .manifesto{padding:125px 20px 150px!important}
      .manifesto h1{font-size:clamp(39px,11vw,55px)!important;width:94vw!important}
      .cinema{min-height:160svh!important}
      .cinema-media{top:14px!important;width:calc(100% - 20px)!important;height:calc(100svh - 28px)!important;margin:0 10px!important;border-radius:22px!important}
      .cinema-copy .a{left:7vw!important;top:20vh!important}
      .cinema-copy .b{right:7vw!important;bottom:23vh!important}
      .cinema-copy p{max-width:210px!important;font-size:19px!important;padding:10px 12px!important}
      .cinema-orb{width:64px!important;height:64px!important}
    }
  `;
  document.head.appendChild(style);
})();
