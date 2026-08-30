(()=>{
  const routes=[
    {label:'Home',href:'/'},
    {label:'Personal',href:'/personal.html'},
    {label:'Campus',href:'/campus.html'},
    {label:'Business',href:'/business.html'},
    {label:'Privacy',href:'/privacy-by-design.html'}
  ];
  const normalize=path=>path.replace(/index\.html$/,'').replace(/\.html$/,'').replace(/\/$/,'')||'/';
  const current=normalize(location.pathname);
  const dock=document.querySelector('.route-dock');

  if(dock){
    const oldLast=dock.querySelector('.round:last-child');
    const trigger=document.createElement('button');
    trigger.className='round nova-menu-trigger';
    trigger.type='button';
    trigger.setAttribute('aria-label','Open quick navigation');
    trigger.setAttribute('aria-expanded','false');
    trigger.setAttribute('aria-controls','nova-quick-menu');
    trigger.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>';
    oldLast?.replaceWith(trigger);

    const menu=document.createElement('div');
    menu.className='nova-quick-menu';
    menu.id='nova-quick-menu';
    menu.setAttribute('aria-hidden','true');
    menu.innerHTML=`<div class="nova-quick-menu-head"><span>Go directly to</span><button type="button" aria-label="Close quick navigation">×</button></div><nav aria-label="Quick site navigation">${routes.map(route=>`<a href="${route.href}"${normalize(route.href)===current?' aria-current="page"':''}>${route.label}<span>↗</span></a>`).join('')}</nav><a class="nova-quick-legal" href="/legal.html">Legal, terms & privacy</a>`;
    document.body.appendChild(menu);

    const close=()=>{
      menu.classList.remove('is-open');
      menu.setAttribute('aria-hidden','true');
      trigger.setAttribute('aria-expanded','false');
    };
    const open=()=>{
      menu.classList.add('is-open');
      menu.setAttribute('aria-hidden','false');
      trigger.setAttribute('aria-expanded','true');
      menu.querySelector('a:not([aria-current])')?.focus();
    };
    trigger.addEventListener('click',()=>menu.classList.contains('is-open')?close():open());
    menu.querySelector('button').addEventListener('click',close);
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.classList.contains('is-open')){close();trigger.focus();}});
    document.addEventListener('pointerdown',event=>{if(menu.classList.contains('is-open')&&!menu.contains(event.target)&&!trigger.contains(event.target))close();});
  }

  document.querySelectorAll('.nova-rainbow-end').forEach(section=>{
    let wave=section.querySelector('.pixel-wave');
    if(!wave){
      wave=document.createElement('div');
      wave.className='pixel-wave';
      wave.setAttribute('aria-hidden','true');
      wave.innerHTML='<span></span>'.repeat(14);
      section.appendChild(wave);
    }
    if(!('IntersectionObserver' in window)){wave.classList.add('play');return;}
    new IntersectionObserver(([entry],observer)=>{
      if(!entry.isIntersecting)return;
      wave.classList.add('play');
      observer.disconnect();
    },{threshold:.2}).observe(section);
  });
})();
