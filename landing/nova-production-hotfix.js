(()=>{
  const pricing=document.getElementById('tarifs');
  if(!pricing)return;

  const normalize=node=>{
    const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);
    const texts=[];
    while(walker.nextNode())texts.push(walker.currentNode);
    for(const text of texts){
      const before=text.nodeValue||'';
      const after=before
        .replace(/14-day/gi,'7-day')
        .replace(/14 days/gi,'7 days');
      if(after!==before)text.nodeValue=after;
    }
  };

  normalize(pricing);

  /* Some existing enhancement scripts rebuild the pricing cards after load.
     Keep the displayed trial duration correct without touching their layout. */
  const observer=new MutationObserver(()=>normalize(pricing));
  observer.observe(pricing,{subtree:true,childList:true,characterData:true});
})();
