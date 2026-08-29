(()=>{
  const contexts={
    slack:{label:'Message in Slack',text:'Hey Lucas — can you send me the file when you have a minute? Thanks!'},
    email:{label:'Email to Lucas',text:'Hi Lucas,\n\nCould you send me the file when you have a moment?\n\nThanks in advance.'},
    cursor:{label:'Instruction in Cursor',text:'Locate the project file, attach it to the current task, and let Lucas know when it is ready to review.'}
  };

  const output=document.querySelector('.context-output');
  const outputLabel=document.querySelector('[data-output-label]');
  const outputText=document.querySelector('[data-output-text]');
  const tabs=[...document.querySelectorAll('[data-context]')];
  let changeTimer;

  tabs.forEach(tab=>tab.addEventListener('click',()=>{
    const next=contexts[tab.dataset.context];
    if(!next||tab.getAttribute('aria-selected')==='true')return;
    tabs.forEach(item=>item.setAttribute('aria-selected',String(item===tab)));
    output.classList.add('is-changing');
    clearTimeout(changeTimer);
    changeTimer=setTimeout(()=>{
      outputLabel.textContent=next.label;
      outputText.textContent=next.text;
      output.classList.remove('is-changing');
    },150);
  }));

  const header=document.querySelector('[data-header]');
  const updateHeader=()=>header?.classList.toggle('is-scrolled',scrollY>18);
  addEventListener('scroll',updateHeader,{passive:true});
  updateHeader();

  const menuButton=document.querySelector('[data-menu-button]');
  const mobileNav=document.querySelector('[data-mobile-nav]');
  const closeMenu=()=>{
    if(!menuButton||!mobileNav)return;
    menuButton.setAttribute('aria-expanded','false');
    menuButton.setAttribute('aria-label','Open navigation');
    mobileNav.hidden=true;
  };
  menuButton?.addEventListener('click',()=>{
    const open=menuButton.getAttribute('aria-expanded')!=='true';
    menuButton.setAttribute('aria-expanded',String(open));
    menuButton.setAttribute('aria-label',open?'Close navigation':'Open navigation');
    mobileNav.hidden=!open;
  });
  mobileNav?.querySelectorAll('a').forEach(link=>link.addEventListener('click',closeMenu));
  addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu()});
})();
