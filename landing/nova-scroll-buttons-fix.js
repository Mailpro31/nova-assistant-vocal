(()=>{
  const style=document.createElement('style');
  style.textContent=`
    /* Every chapter CTA uses the exact compact Try Nova footprint. */
    .chapter .black-btn,
    html body #voice .chapter-inner>a.black-btn{
      width:108px!important;
      min-width:108px!important;
      max-width:108px!important;
      height:36px!important;
      min-height:36px!important;
      padding:0 7px!important;
      box-sizing:border-box!important;
      margin-left:auto!important;
      margin-right:auto!important;
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
      text-align:center!important;
      white-space:nowrap!important;
      font-size:9px!important;
      line-height:1!important;
      letter-spacing:-.025em!important;
      border-radius:999px!important;
      box-shadow:0 8px 20px rgba(0,0,0,.10)!important;
    }
    html body #voice .chapter-inner>a.black-btn{margin-bottom:62px!important}

    /* Remove the sticky/pinned scroll phase from the pastel section. */
    .cinema{
      position:relative!important;
      min-height:100svh!important;
      height:auto!important;
      overflow:hidden!important;
      background:#fff!important;
    }
    .cinema-media{
      position:relative!important;
      top:auto!important;
      left:auto!important;
      width:100%!important;
      height:100svh!important;
      min-height:0!important;
      margin:0!important;
      transform:none!important;
      border-radius:0!important;
      will-change:auto!important;
    }
    .cinema-copy{
      position:absolute!important;
      inset:0!important;
      top:0!important;
      left:0!important;
      width:100%!important;
      height:100%!important;
      min-height:100svh!important;
      margin:0!important;
      transform:none!important;
      opacity:1!important;
      will-change:auto!important;
      pointer-events:none!important;
    }

    @media(max-width:680px){
      .chapter .black-btn,
      html body #voice .chapter-inner>a.black-btn{
        width:108px!important;
        min-width:108px!important;
        max-width:108px!important;
        height:36px!important;
        min-height:36px!important;
        padding:0 6px!important;
        font-size:8.7px!important;
      }
      .cinema{min-height:100svh!important}
      .cinema-media{height:100svh!important}
      .cinema-copy{min-height:100svh!important}
    }
  `;
  document.head.appendChild(style);
})();
