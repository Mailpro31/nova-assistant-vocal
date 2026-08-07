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

    /* Nova Voice: the five white strokes behave like a live speech waveform. */
    #voice .voice-orb .bars{
      display:flex!important;
      align-items:center!important;
      justify-content:center!important;
      gap:5px!important;
      height:34px!important;
      filter:drop-shadow(0 1px 5px rgba(255,255,255,.35));
    }
    #voice .voice-orb .bars i{
      width:4px!important;
      height:18px!important;
      border-radius:999px!important;
      background:#fff!important;
      transform-origin:50% 50%!important;
      will-change:transform,opacity!important;
      animation:voiceSpeechA .78s cubic-bezier(.4,0,.2,1) infinite!important;
      opacity:.96!important;
    }
    #voice .voice-orb .bars i:nth-child(1){animation-name:voiceSpeechA!important;animation-duration:.72s!important;animation-delay:-.31s!important}
    #voice .voice-orb .bars i:nth-child(2){animation-name:voiceSpeechB!important;animation-duration:.91s!important;animation-delay:-.67s!important}
    #voice .voice-orb .bars i:nth-child(3){animation-name:voiceSpeechC!important;animation-duration:.66s!important;animation-delay:-.18s!important}
    #voice .voice-orb .bars i:nth-child(4){animation-name:voiceSpeechB!important;animation-duration:.84s!important;animation-delay:-.52s!important}
    #voice .voice-orb .bars i:nth-child(5){animation-name:voiceSpeechA!important;animation-duration:.74s!important;animation-delay:-.09s!important}
    #voice .voice-orb>.orb{
      animation:voiceListeningBreath 2.8s ease-in-out infinite!important;
    }
    @keyframes voiceSpeechA{
      0%,100%{transform:scaleY(.34);opacity:.78}
      18%{transform:scaleY(.92);opacity:1}
      37%{transform:scaleY(.48);opacity:.88}
      58%{transform:scaleY(1.32);opacity:1}
      79%{transform:scaleY(.63);opacity:.9}
    }
    @keyframes voiceSpeechB{
      0%,100%{transform:scaleY(.58);opacity:.88}
      22%{transform:scaleY(1.42);opacity:1}
      44%{transform:scaleY(.38);opacity:.8}
      66%{transform:scaleY(1.02);opacity:1}
      84%{transform:scaleY(.72);opacity:.92}
    }
    @keyframes voiceSpeechC{
      0%,100%{transform:scaleY(.72);opacity:.92}
      16%{transform:scaleY(1.55);opacity:1}
      34%{transform:scaleY(.54);opacity:.86}
      52%{transform:scaleY(1.18);opacity:1}
      73%{transform:scaleY(.42);opacity:.82}
      88%{transform:scaleY(.94);opacity:1}
    }
    @keyframes voiceListeningBreath{
      0%,100%{transform:scale(1);filter:saturate(1)}
      50%{transform:scale(1.018);filter:saturate(1.06)}
    }
    @media(prefers-reduced-motion:reduce){
      #voice .voice-orb .bars i,#voice .voice-orb>.orb{animation:none!important}
      #voice .voice-orb .bars i{transform:scaleY(.72)!important}
    }

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
      #voice .voice-orb .bars{gap:4px!important}
      #voice .voice-orb .bars i{width:3.5px!important;height:16px!important}
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
