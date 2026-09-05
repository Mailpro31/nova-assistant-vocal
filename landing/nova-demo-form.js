// Amélioration progressive du formulaire de démonstration.
// Sans JS, le formulaire poste nativement vers /api/demo-request (même origine,
// conforme à `form-action 'self'`) et la fonction redirige vers #envoye/#erreur.
// Avec JS, on poste en fetch (même origine, conforme à `connect-src 'self'`)
// pour rester sur la page.
(()=>{
  const form=document.querySelector('[data-demo-form]');
  if(!form)return;
  const status=form.querySelector('[data-demo-status]');
  const submit=form.querySelector('[type="submit"]');
  const say=(kind,key)=>{
    if(!status)return;
    status.textContent=status.dataset[key]||'';
    status.className='demo-status is-visible '+kind;
    status.setAttribute('role','status');
  };

  // Le formulaire natif revient avec un fragment : on affiche le même message.
  if(location.hash==='#envoye'||location.hash==='#erreur'){
    say(location.hash==='#envoye'?'ok':'ko', location.hash==='#envoye'?'ok':'ko');
    // Le fragment n'est l'identifiant d'aucun élément : sans cela le visiteur
    // revenu par l'envoi natif atterrit en haut de page, loin du message.
    status?.scrollIntoView({block:'center'});
  }

  form.addEventListener('submit',async event=>{
    // preventDefault AVANT la validation : le formulaire porte novalidate, donc
    // rien n'empêche l'envoi natif de partir si on rend la main sans l'annuler.
    event.preventDefault();
    if(!form.reportValidity())return;
    submit.disabled=true;
    try{
      const res=await fetch(form.action,{
        method:'POST',
        headers:{'Content-Type':'application/json','Accept':'application/json'},
        body:JSON.stringify(Object.fromEntries(new FormData(form)))
      });
      if(res.ok){form.reset();say('ok','ok');}
      else say('ko','ko');
    }catch{
      say('ko','ko');
    }finally{
      submit.disabled=false;
      status?.scrollIntoView({block:'nearest',behavior:'smooth'});
    }
  });
})();
