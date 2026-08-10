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

    /* All chapter CTAs now use the same compact visual language as Try Nova. */
    .chapter .black-btn{
      width:auto!important;
      min-width:108px!important;
      max-width:176px!important;
      min-height:36px!important;
      height:36px!important;
      padding:0 15px!important;
      font-size:10px!important;
      line-height:1!important;
      margin-left:auto!important;
      margin-right:auto!important;
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
      border-radius:999px!important;
      box-shadow:0 8px 20px rgba(0,0,0,.10)!important;
      white-space:nowrap!important;
    }
    html body #voice .chapter-inner>a.black-btn{
      min-width:108px!important;
      max-width:108px!important;
      width:108px!important;
      margin:0 auto 62px!important;
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

    /* Manifesto: quiet frame, only the Nova bubble moves. */
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

    /* Painterly Nova canvas: soft pastel wash with no hard section edge. */
    .cinema{
      min-height:184svh!important;
      background:#fff!important;
      overflow:clip!important;
    }
    .cinema-media{
      top:0!important;
      width:100%!important;
      height:100svh!important;
      margin:0!important;
      border-radius:0!important;
      overflow:hidden!important;
      transform:none!important;
      background:#fff!important;
      box-shadow:none!important;
      isolation:isolate!important;
    }
    .cinema-media::before{
      content:""!important;
      display:block!important;
      position:absolute!important;
      inset:-12% -7%!important;
      width:auto!important;
      height:auto!important;
      border-radius:0!important;
      background:
        radial-gradient(ellipse 38% 64% at 9% 45%,rgba(106,158,199,.86) 0%,rgba(142,185,215,.68) 33%,transparent 70%),
        radial-gradient(ellipse 33% 50% at 36% 14%,rgba(195,209,239,.56) 0%,rgba(218,225,242,.36) 42%,transparent 72%),
        radial-gradient(ellipse 36% 53% at 58% 76%,rgba(178,216,197,.69) 0%,rgba(211,231,218,.40) 39%,transparent 74%),
        radial-gradient(ellipse 42% 67% at 94% 42%,rgba(242,211,151,.84) 0%,rgba(245,225,184,.64) 36%,transparent 72%),
        radial-gradient(ellipse 26% 36% at 72% 9%,rgba(232,207,224,.38) 0%,transparent 72%),
        linear-gradient(118deg,#d8e9f3 0%,#edf2ee 47%,#f2dfb7 100%)!important;
      filter:blur(30px) saturate(.92)!important;
      opacity:.94!important;
      transform:scale(1.08)!important;
      animation:none!important;
      -webkit-mask-image:linear-gradient(to bottom,transparent 0%,rgba(0,0,0,.35) 5%,#000 15%,#000 82%,rgba(0,0,0,.45) 93%,transparent 100%)!important;
      mask-image:linear-gradient(to bottom,transparent 0%,rgba(0,0,0,.35) 5%,#000 15%,#000 82%,rgba(0,0,0,.45) 93%,transparent 100%)!important;
      z-index:0!important;
    }
    .cinema-media::after{
      content:""!important;
      position:absolute!important;
      inset:0!important;
      z-index:6!important;
      pointer-events:none!important;
      background:
        linear-gradient(180deg,#fff 0%,rgba(255,255,255,.92) 3%,rgba(255,255,255,.28) 11%,transparent 19%,transparent 78%,rgba(255,255,255,.34) 88%,rgba(255,255,255,.94) 97%,#fff 100%)!important;
    }
    .cinema-shape{display:none!important}
    .cinema-orb{
      width:74px!important;
      height:74px!important;
      left:50%!important;
      right:auto!important;
      top:48%!important;
      transform:translate(-50%,-50%)!important;
      animation:novaCinemaMove 6.4s cubic-bezier(.45,0,.55,1) infinite!important;
      z-index:7!important;
      filter:none!important;
    }
    @keyframes novaCinemaMove{
      0%,100%{transform:translate(-50%,-50%) translate3d(-20px,9px,0)}
      31%{transform:translate(-50%,-50%) translate3d(17px,-13px,0)}
      63%{transform:translate(-50%,-50%) translate3d(12px,14px,0)}
      82%{transform:translate(-50%,-50%) translate3d(-10px,-5px,0)}
    }
    .cinema-copy{
      height:100svh!important;
      margin-top:-100svh!important;
      transform:none!important;
      opacity:1!important;
    }
    .cinema-copy p{
      max-width:250px!important;
      padding:0!important;
      border:0!important;
      border-radius:0!important;
      background:transparent!important;
      backdrop-filter:none!important;
      -webkit-backdrop-filter:none!important;
      color:rgba(17,18,23,.78)!important;
      font-size:clamp(16px,1.65vw,23px)!important;
      font-weight:560!important;
      line-height:1.04!important;
      letter-spacing:-.045em!important;
      text-shadow:0 1px 18px rgba(255,255,255,.32)!important;
    }
    .cinema-copy .a{left:9vw!important;top:29vh!important;text-align:left!important}
    .cinema-copy .b{right:9vw!important;top:auto!important;bottom:27vh!important;text-align:right!important}
    .cinema-copy small{
      bottom:7vh!important;
      color:rgba(17,18,23,.46)!important;
      letter-spacing:.18em!important;
    }

    @media(max-width:680px){
      .chapter .black-btn{
        min-width:104px!important;
        max-width:164px!important;
        height:34px!important;
        min-height:34px!important;
        padding:0 13px!important;
        font-size:9.5px!important;
      }
      html body #voice .chapter-inner>a.black-btn{
        width:102px!important;
        min-width:102px!important;
        max-width:102px!important;
        height:34px!important;
        min-height:34px!important;
        margin-bottom:54px!important;
      }
      .dock.dock-compact{grid-template-columns:40px minmax(154px,170px) 40px!important}
      .dock.dock-compact a,.dock.dock-compact button,.dock.dock-compact .legal-link{width:40px!important;height:40px!important}
      .dock.dock-compact .main{width:100%!important;min-width:0!important;height:40px!important}
      .manifesto{padding:125px 20px 150px!important}
      .manifesto h1{font-size:clamp(39px,11vw,55px)!important;width:94vw!important}
      .cinema{min-height:168svh!important}
      .cinema-media::before{inset:-10% -18%!important;filter:blur(24px) saturate(.92)!important}
      .cinema-copy .a{left:7vw!important;top:22vh!important}
      .cinema-copy .b{right:7vw!important;bottom:22vh!important}
      .cinema-copy p{max-width:205px!important;font-size:18px!important}
      .cinema-orb{width:62px!important;height:62px!important}
      .cinema-copy small{bottom:7.5vh!important;width:78vw!important;text-align:center!important;white-space:normal!important}
    }
  `;
  document.head.appendChild(style);
})();
