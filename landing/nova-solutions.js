(()=>{
  document.body.classList.add('reveal-ready');
  const items=[...document.querySelectorAll('.reveal')];
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){
    items.forEach(item=>item.classList.add('in'));
  }else{
    const observer=new IntersectionObserver(entries=>{
      entries.forEach(entry=>{
        if(!entry.isIntersecting)return;
        entry.target.classList.add('in');
        observer.unobserve(entry.target);
      });
    },{threshold:.13,rootMargin:'0px 0px -7%'});
    items.forEach(item=>observer.observe(item));
  }
  const dock=document.querySelector('.route-dock');
  let ticking=false;
  addEventListener('scroll',()=>{
    if(ticking)return;
    ticking=true;
    requestAnimationFrame(()=>{
      dock?.classList.toggle('scrolling',scrollY>40);
      ticking=false;
    });
  },{passive:true});
})();
