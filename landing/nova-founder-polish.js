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
    .founder-story{position:relative;min-height:100svh;display:grid;place-items:center;padding:90px 24px;background:#fff;overflow:hidden}
    .founder-story img{display:block;width:min(760px,88vw);height:auto;object-fit:contain;mix-blend-mode:multiply}
    @media(max-width:680px){.dots.chapter-rail{display:none!important}.founder-story{min-height:auto;padding:72px 18px}.founder-story img{width:min(560px,96vw)}}
  `;
  document.head.appendChild(style);

  const rail=document.querySelector('.dots');
  if(rail){
    rail.classList.add('chapter-rail');
    rail.setAttribute('aria-label','Progression');
    [...rail.querySelectorAll('a')].forEach((link,index)=>{
      link.textContent='';
      link.setAttribute('aria-label',['Local','Styles','Context','Voice'][index]||`Section ${index+1}`);
    });
  }

  document.querySelectorAll('.founder-story').forEach(el=>el.remove());
  const pricing=document.querySelector('.pricing');
  if(pricing){
    const section=document.createElement('section');
    section.className='founder-story';
    section.setAttribute('aria-label','Mot du fondateur');
    const img=document.createElement('img');
    img.src='/sasha-founder.webp';
    img.alt='Portrait en demi-teinte de Sasha, fondateur de Nova, avec un mot personnel.';
    img.loading='eager';
    img.decoding='async';
    section.appendChild(img);
    pricing.before(section);
  }
})();
