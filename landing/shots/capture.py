# Captures authentiques de l'app Nova (ui/dock.html) pour la landing.
# Rendu 2x (retina), fond pastel discret derrière les surfaces en verre.
import os
from playwright.sync_api import sync_playwright

DOCK = "file://" + os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ui", "dock.html"))
OUT = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)

# état réaliste injecté (l'API pywebview est absente en capture)
STATE = """
S.modes=[{id:'auto',label:'Automatique'},{id:'voice_to_text',label:'Normal'},
 {id:'email',label:'E-mail'},{id:'prompt_engineer',label:'Prompt IA'},
 {id:'todo',label:'To-do list'},{id:'messages',label:'Messages'},{id:'notes',label:'Prise de notes'}];
S.mode='auto';S.tier='ultra';S.cloud_enabled=true;S.autostart=true;S.ptt_key='f9';
S.profile='high';
S.profiles=[{id:'normal',label:'Normal'},{id:'high',label:'Élevé',warning:''},
 {id:'ultra',label:'Ultra',locked:true,reason:'Nécessite plus de mémoire'}];
S.hardware={ram_total_gb:16,has_gpu:true,gpu_name:'accélération graphique NVIDIA'};
S.lic={tier:'ultra',active:true,email:'vous@exemple.fr',quota:{limit:null}};
S.perso={orb:true,modes:true,turbo:true};
S.custom_modes=[
 {name:'Jira',match:['jira','sprint'],prompt:'Reformule en ticket : titre, contexte, critères d\\u2019acceptation.'},
 {name:'CRM',match:['salesforce'],prompt:'Compte-rendu d\\u2019appel : client, besoin, prochaine étape.'}];
S.languages=[{code:'auto',label:'Auto (détection)'},{code:'fr',label:'Français'},{code:'en',label:'English'}];
S.language='auto';
S.custom_vars=[{trigger:'mon IBAN',value:'FR76 3000 4000 5600 0000 1234 567'}];
"""

BACKDROP = """
const bd=document.createElement('div');
bd.style.cssText='position:fixed;inset:0;z-index:-1;background:'
 +'radial-gradient(90% 80% at 20% 12%,#2b3040 0%,transparent 60%),'
 +'radial-gradient(80% 70% at 82% 88%,#332e42 0%,transparent 62%),'
 +'linear-gradient(160deg,#191b22,#14151b)';
document.body.appendChild(bd);
document.documentElement.style.setProperty('--font','"Liberation Sans",sans-serif');
"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
              "--force-color-profile=srgb", "--disable-lcd-text"])

    # ---- 1 & 2 : fenêtre Réglages (la webview fait 880×620 : la page EST la fenêtre)
    pg = b.new_page(viewport={"width": 880, "height": 620}, device_scale_factor=2)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(DOCK)
    pg.wait_for_timeout(500)
    pg.evaluate(STATE + BACKDROP + "openSettings();")
    pg.wait_for_timeout(400)
    pg.evaluate("CAT='cmodes';buildSidebar();buildPane();")
    pg.wait_for_timeout(250)
    pg.screenshot(path=f"{OUT}/app-styles.png")
    pg.evaluate("CAT='general';buildSidebar();buildPane();")
    pg.wait_for_timeout(250)
    pg.screenshot(path=f"{OUT}/app-reglages.png")
    pg.close()

    # ---- 3 : dock + menu des Styles ouvert (7 Styles, icônes colorées)
    pg = b.new_page(viewport={"width": 430, "height": 470}, device_scale_factor=2)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(DOCK)
    pg.wait_for_timeout(600)
    pg.evaluate(STATE + BACKDROP + """
document.getElementById('modes').classList.add('on');renderModes();
""")
    pg.wait_for_timeout(700)          # laisse l'orbe WebGL s'animer
    pg.screenshot(path=f"{OUT}/app-menu-styles.png")
    pg.close()

    # ---- 4 : dock en écoute, bulle « Je t'écoute… »
    pg = b.new_page(viewport={"width": 430, "height": 200}, device_scale_factor=2)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(DOCK)
    pg.wait_for_timeout(600)
    pg.evaluate(STATE + BACKDROP + """
window.novaShow('listening',"Je t'écoute…");window.novaLevel(0.06);
""")
    pg.wait_for_timeout(650)
    pg.evaluate("window.novaLevel(0.08);")
    pg.wait_for_timeout(120)
    pg.screenshot(path=f"{OUT}/app-ecoute.png")
    pg.close()
    b.close()
    if errs:
        raise SystemExit("erreurs page: " + "; ".join(errs[:4]))

print("captures OK:", sorted(os.listdir(OUT)))
