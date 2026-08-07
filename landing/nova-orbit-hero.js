(()=>{
  const film=document.getElementById('film');
  const enter=document.getElementById('enter');
  if(!film)return;

  const snapToPastel=()=>{
    const y=film.getBoundingClientRect().top+window.scrollY;
    window.scrollTo({top:y,left:0,behavior:'auto'});
  };

  // The pastel cinematic is now the first real screen. Prevent browser scroll
  // restoration from exposing a stale position behind the fixed intro.
  if('scrollRestoration' in history)history.scrollRestoration='manual';
  requestAnimationFrame(()=>window.scrollTo(0,0));

  if(enter){
    enter.addEventListener('click',()=>setTimeout(snapToPastel,660));
  }

  addEventListener('keydown',e=>{
    if((e.key==='Enter'||e.key===' ')&&document.body.classList.contains('ready')){
      setTimeout(snapToPastel,0);
    }
  });

  const observer=new MutationObserver(()=>{
    if(document.body.classList.contains('ready')){
      requestAnimationFrame(snapToPastel);
      observer.disconnect();
    }
  });
  observer.observe(document.body,{attributes:true,attributeFilter:['class']});
})();
