(()=>{
  const style=document.createElement('style');
  style.textContent=`
    /* Every editorial chapter CTA uses the exact Try Nova footprint. */
    html body .experience .chapter .chapter-inner>a.black-btn,
    html body #voice .chapter-inner>a.black-btn{
      width:108px!important;
      min-width:108px!important;
      max-width:108px!important;
      height:36px!important;
      min-height:36px!important;
      max-height:36px!important;
      padding:0 6px!important;
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
      letter-spacing:-.03em!important;
      border-radius:999px!important;
      box-shadow:0 8px 20px rgba(0,0,0,.10)!important;
      transform:none!important;
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
      html body .experience .chapter .chapter-inner>a.black-btn,
      html body #voice .chapter-inner>a.black-btn{
        width:108px!important;
        min-width:108px!important;
        max-width:108px!important;
        height:36px!important;
        min-height:36px!important;
        max-height:36px!important;
        padding:0 5px!important;
        font-size:8.5px!important;
      }
      .cinema{min-height:100svh!important}
      .cinema-media{height:100svh!important}
      .cinema-copy{min-height:100svh!important}
    }
  `;
  document.head.appendChild(style);

  const forceTryNovaSize=()=>{
    document.querySelectorAll('.experience .chapter .chapter-inner>a.black-btn').forEach(btn=>{
      const long=btn.textContent.trim().length>14;
      const props={
        width:'108px',minWidth:'108px',maxWidth:'108px',height:'36px',minHeight:'36px',maxHeight:'36px',
        padding:'0 5px',boxSizing:'border-box',display:'inline-flex',alignItems:'center',justifyContent:'center',
        textAlign:'center',whiteSpace:'nowrap',lineHeight:'1',borderRadius:'999px',transform:'none',
        fontSize:long?'8.2px':'9px',letterSpacing:'-.03em',marginLeft:'auto',marginRight:'auto'
      };
      Object.entries(props).forEach(([key,value])=>btn.style.setProperty(key.replace(/[A-Z]/g,m=>'-'+m.toLowerCase()),value,'important'));
    });
  };

  forceTryNovaSize();
  [60,180,400,800,1400,2200,3200].forEach(delay=>setTimeout(forceTryNovaSize,delay));
  new MutationObserver(forceTryNovaSize).observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});
})();
