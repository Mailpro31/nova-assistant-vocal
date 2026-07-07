# -*- coding: utf-8 -*-
"""
Modes intelligents contextuels (portés de RoadSpeak) :
Message / Navigation / Média / Appel / Mémo / Urgence / Profil — règles
rapides d'abord (offline, instantané), automatisations de l'utilisateur,
puis IA en secours. Chaque interaction part dans l'historique SQLite.
"""

import os
import random
import re
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta

import core
import files_mode
import fun_mode
import integrations
import storage
import timers
import winext

MEDIA_ACTIONS = [
    (re.compile(r"\b(pause|met(?:s|tre)? en pause|stopp(?:e|es|er) la (musique|lecture)|arret(?:e|er) la musique)\b"), "playPause"),
    (re.compile(r"\b(chanson|musique|piste|morceau) suivante?\b|\bsuivante?\b|\bskip\b"), "next"),
    (re.compile(r"\b(chanson|musique|piste|morceau) precedente?\b|\bprecedente?\b|\breviens en arriere\b"), "prev"),
    (re.compile(r"\b(mont(?:e|es|er|ez) le (son|volume)|plus fort|augment(?:e|es|er|ez) le (son|volume))\b"), "volUp"),
    (re.compile(r"\b(baiss(?:e|es|er|ez) le (son|volume)|moins fort|diminu(?:e|es|er|ez) le (son|volume))\b"), "volDown"),
    (re.compile(r"\b(coup(?:e|es|er|ez) le son|remet(?:s|tre)? le son|mute)\b"), "mute"),
    (re.compile(r"\b(joue|remet(?:s|tre)? la musique|met(?:s|tre)? (de )?la musique|lance la musique|play|reprend(?:s|re)? la (musique|lecture))\b"), "playPause"),
]

# mots « transparents » autour d'une commande média : politesse, articles,
# vocabulaire du domaine — tout autre mot signifie que la demande est plus
# riche qu'une simple commande média et doit partir vers l'IA planificatrice
_MEDIA_GLUE = {
    "nova", "stp", "svp", "s'il", "te", "vous", "plait", "merci", "maintenant",
    "vite", "donc", "alors", "la", "le", "les", "l'", "de", "du", "des", "d'",
    "un", "une", "et", "a", "au", "aux", "sur", "dans", "pour", "moi", "me",
    "peu", "encore", "tout", "bien", "fort", "s'il", "musique", "chanson",
    "son", "volume", "lecture", "piste", "morceau", "video",
}

RE_NAVIGATION = re.compile(
    r"^(?:va|vas|allons|emmene[- ]?(?:moi|nous)|conduis[- ]?(?:moi|nous)|navigue|itineraire"
    r"|direction|guide[- ]?moi)\b\s*(?:jusqu ?a|vers|a|au|aux|chez|pour)?\s*(.+)$")
RE_CALL = re.compile(r"^(?:appelle|telephone a|passe un appel a|appeler)\s+(.+)$")
RE_MSG_TO = re.compile(
    r"^(?:envoie|envoyer|ecris|redige)\s+(?:un\s+|une\s+)?"
    r"(?:(?:message|sms|texto|mail|email|courriel|whatsapp)\s*)*"
    r"(?:a|au|aux)\s+([a-z\- ]+?)\s+(?:pour (?:lui|leur) dire|disant|qui dit|que|:)?\s*(.+)$")
RE_MSG_DIS = re.compile(r"^dis (?:a|au|aux)\s+([a-z\- ]+?)\s+(?:que|de|d)\s+(.+)$")
RE_MSG_FREE = re.compile(r"^(?:message|sms|texto)\b\s*(?::)?\s*(.+)$")
RE_PROFILE = re.compile(r"^(?:change (?:de |le )?profil|passe au profil|profil suivant)\s*(?:vers|a|au|de)?\s*(.*)$")

RE_TIMER_CANCEL = re.compile(
    r"^(?:annule|arrete|stoppe|coupe|oublie) (?:le |la |les |mon |ma |mes "
    r"|ce |cette |tous les )?"
    r"(?:minuteurs?|rappels?|minuterie|comptes? a rebours|chrono(?:metre)?s?|timer)")
RE_REMIND_A = re.compile(r"^rappelle[- ]?moi\s+dans\s+(.+?)\s+(?:de |d')(.+)$")
RE_REMIND_B = re.compile(r"^rappelle[- ]?moi\s+(?:de |d')?(.*?)\s*dans\s+(.+)$")
# le mot-clé peut être N'IMPORTE OÙ : la transcription vocale déforme souvent
# le début (« mets un minuteur » entendu « meilleur minuteur », « mais un
# minuteur »…) — c'est la durée qui valide l'intention, pas le verbe
RE_TIMER_WORD = re.compile(
    r"\b(?:minuteurs?|minuterie|comptes? a rebours|chrono(?:metre)?s?|timer)\b")
RE_TIME = re.compile(
    r"^(?:dis[- ]moi )?(?:quelle heure|il est quelle heure|il est combien|l'heure"
    r"|quel jour|on est quel jour|quelle date|quelle est la date"
    r"|quel mois|on est quel mois|quelle annee|on est (?:en )?quelle annee)")
RE_WEATHER = re.compile(r"\b(?:meteo|quel temps|quelle temperature)\b")
RE_WEATHER_CITY = re.compile(r"\b(?:a|au|aux|sur|pour)\s+([a-z' \-]{2,})$")
RE_MUSIC = re.compile(
    r"^(?:mets?|joue|lance|ecoute)\s+(.+?)\s+sur\s+(youtube music|youtube|spotify|deezer)\s*$")
# « joue du jazz » sans service (JARVIS) : Spotify si connecté, sinon YouTube
RE_MUSIC_NOSVC = re.compile(
    r"^(?:joue|mets?|ecoute)\s+(?:du |de la |un peu de )(.+)$")

# volume précis (« mets le volume à 30 % ») et son par application
RE_VOL_SET = re.compile(
    r"^(?:mets?|regle|monte|baisse|descends?|passe) (?:le |la |du )?(?:son|volume)"
    r" (?:a|sur) (\d{1,3})\s*(?:%|pour ?cents?)?$")
RE_VOL_BARE = re.compile(r"^volume (?:a |sur )?(\d{1,3})\s*(?:%|pour ?cents?)?$")
RE_VOL_REL = re.compile(
    r"^(monte|augmente|baisse|diminue|descends?) le (?:son|volume)"
    r" (?:de |d')(\d{1,3})\s*(?:%|points?|pour ?cents?)?$")
RE_APP_MUTE = re.compile(
    r"^(coupe|remets?|retablis|reactive) le son (?:de |du |d'|des )(.+)$")

# fenêtres : « bascule sur word », « mets chrome et word côte à côte »
RE_WIN_FOCUS = re.compile(r"^(?:bascule|reviens|retourne) (?:sur|a|vers) (.+)$")
RE_WIN_FOCUS2 = re.compile(
    r"^(?:affiche|montre|mets?|passe|va|bascule) (?:sur |a |vers )?la fenetre"
    r" (?:de |du |d')?(.+)$")
RE_WIN_SPLIT = re.compile(
    r"^mets? (.+?) et (.+?) (?:cote a cote|en split(?: screen)?|en partage d'ecran)$")

# domotique Home Assistant : lumières, prises, couleurs, luminosité
COULEURS_RGB = {
    "rouge": [255, 0, 0], "bleu": [0, 0, 255], "vert": [0, 255, 0],
    "blanc": [255, 255, 255], "orange": [255, 140, 0], "violet": [148, 0, 211],
    "rose": [255, 20, 147], "jaune": [255, 255, 0], "cyan": [0, 255, 255],
    "turquoise": [64, 224, 208], "or": [255, 215, 0], "magenta": [255, 0, 255],
    "lavande": [230, 230, 250], "corail": [255, 127, 80], "indigo": [75, 0, 130],
}
RE_LIGHT_ON = re.compile(
    r"^allume(?:r|z)?(?: la| les| le| l')?\s*(?:lumi[eè]res?|lampes?)?\s*"
    r"(?:du |de la |de l'|des |dans (?:le |la |l')?)?(.*)$")
RE_LIGHT_OFF = re.compile(
    r"^(?:eteins|eteindre|eteignez|coupe(?:r|z)?)(?: la| les| le| l')?\s*"
    r"(?:lumi[eè]res?|lampes?)?\s*(?:du |de la |de l'|des |dans (?:le |la |l')?)?(.*)$")
RE_LIGHT_COLOR = re.compile(
    r"^mets?\s+(?:la lumi[eè]re (?:du |de la |de l'|des )?)?(.*?)\s+en\s+(\w+)$")
RE_LIGHT_PCT = re.compile(
    r"^(?:mets?|regle|baisse|monte) (?:la )?(?:lumi[eè]re|luminosite|lampe)"
    r"(?: (?:du |de la |de l'|des )?(.*?))? (?:a |sur )?(\d{1,3})"
    r"\s*(?:%|pour ?cents?)?$")
RE_PLUG = re.compile(
    r"^(allume|eteins|coupe|active|desactive|branche|debranche)"
    r"(?:r|z)?\s+(?:la |le |les )?prise\s+(?:du |de la |de l'|des )?(.*)$")
RE_TEMP = re.compile(
    r"^(?:quelle (?:est la |)temperature|il fait combien|combien il fait)"
    r"\s*(?:dans (?:le |la |l')?|du |de la |de l'|au )?(.*?)\s*\??$")

# listes vocales (courses, à faire…)
RE_LIST_ADD = re.compile(
    r"^(?:ajoute|rajoute)\s+(.+?)\s+(?:a|à|dans|sur)\s+(?:ma |la |mes )?"
    r"liste(?:\s+(?:de\s+)?(courses|achats|taches|t[aâ]ches|a faire|à faire))?$")
RE_LIST_SHOW = re.compile(
    r"^(?:montre|affiche|lis|donne)(?:[- ]moi)?\s+(?:ma |la |mes )?"
    r"liste(?:\s+(?:de\s+)?(courses|achats|taches|t[aâ]ches|a faire|à faire))?$"
    r"|^(?:qu'ai[- ]je|qu'est[- ]ce que j'ai) (?:dans (?:ma |la )?liste"
    r"|a acheter|à acheter)")
RE_LIST_CLEAR = re.compile(
    r"^(?:vide|efface|supprime|nettoie)\s+(?:ma |la |mes )?"
    r"liste(?:\s+(?:de\s+)?(courses|achats|taches|t[aâ]ches))?$")

# fichiers à la voix
RE_SORT = re.compile(
    r"^(?:trie|range|organise|classe)(?:r|z)?\s+(?:mes |mon |le |la |les )?(.+)$")
RE_FIND_FILE = re.compile(
    r"^(?:trouve|cherche|retrouve|ou est|où est)(?:r|z|[- ]moi)?\s+"
    r"(?:le |la |mon |ma |mes |un |une )?fichier\s+(.+)$")
RE_LIST_FOLDER = re.compile(
    r"^(?:liste|montre|affiche|qu'y a[- ]t[- ]il dans)(?:r|z|[- ]moi)?\s+"
    r"(?:le contenu de |mon |mes |le |la )?(.+)$")

# mémoire longue : « souviens-toi que ma plaque est AB-123-CD »
RE_REMEMBER = re.compile(
    r"^(?:souviens[- ]toi|retiens|memorise) (?:que |qu'|de |d')?(.+)$")
RE_FORGET = re.compile(r"^oublie (?:que |qu'|ce que je t'ai dit sur )?(.+)$")

# briefing vocal : heure + météo + minuteurs + mails en une réponse
RE_BRIEFING = re.compile(
    r"^(?:mon |le )?briefing$|^(?:fais|donne)[- ]moi (?:le |mon )?briefing$"
    r"|^(?:resume|raconte)(?:[- ]moi)? (?:ma|la) journee$|^quoi de neuf$"
    r"|^bonjour(?: nova)?$")

# lecture des mails (compte Google connecté), sinon on ouvre Gmail
RE_MAILS = re.compile(
    r"^(?:lis|lecture de|donne|montre|affiche)(?:[- ]moi)? (?:mes |les )?"
    r"(?:\d+ )?(?:derniers |nouveaux )?(?:e-?mails?|mails?|courriels?)$")

# clic par vision : « clique sur le bouton lecture », « clique sur play »
RE_CLICK = re.compile(
    r"^(?:clique|clic|appuie|appuyer|tape)(?:r|z)?\s+(?:sur\s+)?(?:le |la |l'|les |sur )?(.+)$")

# vision : la demande porte sur ce qui est affiché à l'écran — élargi car
# à l'oral on dit surtout « regarde ça », « qu'est-ce que tu vois ? »
RE_SCREEN = re.compile(
    r"\b(?:mon ecran|l'ecran|a l'ecran|cette page|cette fenetre|cet onglet"
    r"|ce mail|cet e-?mail|ce message|ce document|ce texte|ce tableau"
    r"|cette image|cette video|cette erreur|ce site|cet article"
    r"|ce que je regarde|ce qui est affiche|ce qui s'affiche|devant moi"
    r"|qu'est[- ]ce que tu vois|tu vois quoi|que vois[- ]tu|vois[- ]tu"
    r"|dis[- ]moi ce que tu vois|decris ce que tu vois)\b"
    r"|^(?:regarde|lis|resume|decris|explique|traduis|analyse|corrige|aide[- ]moi avec)"
    r"(?:[- ]moi)?\s+(?:ca|ceci|cela)\b")
RE_CALENDAR = re.compile(
    r"^(?:ajoute|cree|mets?|planifie|programme|note)\s+(?:un |une )?"
    r"(?:rendez[- ]?vous|rdv|evenement|reunion)\b\s*(.*)$")

# ── rappels à heure FIXE (JARVIS) : « rappelle-moi le sport à 15 h 30 »,
#    « rappelle-moi à 9 h de prendre le médicament », option quotidienne
RE_REMIND_AT_A = re.compile(
    r"^rappelle[- ]?moi\s+(?:de |d')?(.+?)\s+(?:a|à)\s+(\d{1,2})\s*(?:h(?:eures?)?|:)"
    r"\s*(\d{1,2})?\s*(tous les jours|chaque jour|quotidien(?:nement)?)?\s*$")
RE_REMIND_AT_B = re.compile(
    r"^rappelle[- ]?moi\s+(?:a|à)\s+(\d{1,2})\s*(?:h(?:eures?)?|:)\s*(\d{1,2})?"
    r"\s+(?:de |d')(.+)$")

# ── ajustement / comptage de minuteurs (JARVIS)
RE_TIMER_ADJ_ADD = re.compile(
    r"^(?:ajoute|rajoute)\s+(.+?)\s+(?:au|sur le)\s+(?:minuteur|chrono(?:metre)?|timer)$")
RE_TIMER_ADJ_SUB = re.compile(
    r"^(?:retire|enleve|diminue)\s+(.+?)\s+(?:au|du|sur le)\s+(?:minuteur|chrono(?:metre)?|timer)$")
RE_TIMER_COUNT = re.compile(
    r"^combien de (?:minuteurs?|rappels?)|^combien de temps (?:il )?reste"
    r"|^temps restant|^il reste combien de temps")

# ── fermeture d'application (JARVIS) : validée contre les applis connues
RE_CLOSE_APP = re.compile(r"^(?:ferme|quitte|stoppe)\s+(.+)$")

# ── alimentation du PC (JARVIS, avec garde-fou de confirmation)
RE_POWER_SLEEP = re.compile(
    r"^met(?:s|tre)? (?:le pc |l'ordinateur |l'ordi )?en veille$|^mode veille$")
RE_POWER_OFF = re.compile(
    r"^(?:eteins|arrete) (?:le pc|l'ordinateur|l'ordi|mon pc)"
    r"(?:\s+dans\s+(.+))?$")
RE_POWER_REBOOT = re.compile(r"^redemarre (?:le pc|l'ordinateur|l'ordi|mon pc)$")
RE_POWER_CANCEL = re.compile(
    r"^annule (?:l[' ]arret|l[' ]extinction|le redemarrage)(?: du pc)?$")
RE_POWER_CONFIRM = re.compile(r"^confirme l[' ]arret(?: du pc)?$")

# ── luminosité de l'écran (JARVIS) — après la domotique : « mets la lumière
#    du salon à 40 % » reste Home Assistant
RE_BRIGHT_SET = re.compile(
    r"^(?:mets?|regle|baisse|monte|augmente|diminue) (?:la )?luminosite"
    r"(?: de l'ecran)?(?: a| sur)? (\d{1,3})\s*(?:%|pour ?cents?)?$")
RE_BRIGHT_REL = re.compile(
    r"^(monte|augmente|baisse|diminue|reduis) (?:la )?luminosite(?: de l'ecran)?$")

# ── heure dans une autre ville (avant RE_TIME)
RE_TIME_CITY = re.compile(
    r"^(?:quelle heure (?:est[- ]il|il est)?|il est quelle heure)\s*(?:a|à|au|aux)\s+(.+?)\s*\??$")

# ── infos locales (JARVIS) : capitales, monnaies, épellation, alphabet OTAN
RE_CAPITALE = re.compile(
    r"^(?:quelle est la |c'est quoi la |donne[- ]moi la )?capitale"
    r"\s+(?:de la |de l'|du |des |de )(.+?)\s*\??$")
RE_MONNAIE = re.compile(
    r"^(?:quelle est la |c'est quoi la )?(?:monnaie|devise)"
    r"\s+(?:de la |de l'|du |des |de |en |aux? )(.+?)\s*\??$")
RE_SPELL = re.compile(
    r"^(?:epelle|epeler|comment (?:ca )?s'ecrit)\s+(?:le mot )?(.+?)\s*\??$")
RE_OTAN = re.compile(r"^([a-z]) comme (?:quoi|dans quoi)\s*\??$")

# ── fun : blagues, citations, tirages (JARVIS)
RE_JOKE = re.compile(
    r"\b(?:raconte|dis)[- ]?(?:moi)?\s+une blague\b|^une blague$|^blague$"
    r"|^fais[- ]moi rire$")
RE_QUOTE = re.compile(
    r"\bune citation\b|^citation$|^motive[- ]moi$|^phrase inspirante$")
RE_COIN = re.compile(r"^pile ou face\s*\??$|^lance une piece$")
RE_DICE = re.compile(r"^(?:lance|jette) (?:un|le) de(?: a (\d+) faces)?$")
RE_RANDNUM = re.compile(
    r"^(?:donne[- ]moi )?un nombre(?: aleatoire| au hasard)?"
    r"(?: entre (\d+) et (\d+))?$")
RE_PASSWORD = re.compile(
    r"^(?:genere|cree|donne)(?:[- ]moi)? un mot de passe"
    r"(?: (?:de|a) (\d{1,2}) caracteres?)?$")
RE_COUNTDOWN = re.compile(
    r"combien de jours (?:avant|jusqu'a)|c'est quand noel|c'est dans combien de temps noel")

# ── système : batterie, CPU, RAM, uptime, corbeille (JARVIS)
RE_SYS_BATT = re.compile(
    r"^(?:il reste )?combien de batterie|niveau de (?:la )?batterie"
    r"|^(?:ma |la )batterie\s*\??$|batterie restante")
RE_SYS_CPU = re.compile(
    r"utilisation (?:du )?(?:processeur|cpu)|(?:le )?(?:cpu|processeur) est a combien")
RE_SYS_RAM = re.compile(
    r"utilisation (?:de la )?(?:memoire|ram)|(?:la )?ram est a combien")
RE_SYS_UP = re.compile(
    r"depuis combien de temps (?:le pc|l'ordinateur|l'ordi) est allume|^uptime$")
RE_TRASH = re.compile(r"^(?:vide(?:r|z)?|nettoie) la corbeille$")

# ── fichiers étendus (JARVIS) : création de dossier, mosaïque, capture
RE_MKDIR = re.compile(
    r"^cree (?:un |le )?(?:nouveau )?dossier (?:appele |nomme )?(.+?)"
    r"(?:\s+dans\s+(?:mes |mon |les |le )?(\w+))?$")
RE_QUAD = re.compile(
    r"^(?:ouvre|affiche|montre) (?:mes|les) (?:quatre |4 )?dossiers"
    r"(?: personnels| perso| principaux)?$")
RE_FULLSHOT = re.compile(
    r"^(?:prends?|fais|capture)(?:[- ]moi)? (?:une )?capture(?: d'ecran)?"
    r" (?:complete|entiere|de (?:tout )?l'ecran)$|^capture complete$")

# ── agenda Google (lecture) — AVANT resolve_open (« mon agenda » ≠ ouvrir le site)
RE_AGENDA = re.compile(
    r"^(?:quel est |c'est quoi |donne[- ]moi |montre[- ]moi |lis[- ]moi )?"
    r"(?:mon |l')agenda(?: du jour| d'aujourd'hui| de la semaine)?\s*\??$"
    r"|^mes (?:prochains )?(?:rendez[- ]?vous|evenements)\s*\??$"
    r"|^qu'est[- ]ce que j'ai (?:de prevu|au programme)"
    r"(?: aujourd'hui| demain| cette semaine)?\s*\??$")

# ── Google Docs / Sheets à la voix (si compte connecté)
RE_GDOC_CREATE = re.compile(
    r"^cree (?:un )?(?:nouveau )?(?:google )?doc(?:ument)?(?: google)?"
    r"(?: (?:appele|nomme) (.+))?$")
RE_GDOC_APPEND = re.compile(
    r"^(?:ajoute|ecris|note) (.+) dans (?:le|mon) doc(?:ument)?$")
RE_GSHEET = re.compile(
    r"^cree (?:un )?(?:nouveau )?(?:tableur|google sheet|"
    r"(?:une )?feuille de calcul)(?: (?:appele|nomme) (.+))?$")

# ── scan antivirus Windows Defender (phrase explicite)
RE_AV = re.compile(
    r"^(?:lance|demarre|fais) (?:un |une )?(?:scan|analyse) antivirus$"
    r"|^(?:scan|analyse) antivirus$")

# ── recherche d'images (JARVIS, version navigateur) — AVANT resolve_open
RE_IMAGES = re.compile(
    r"^(?:montre|affiche|cherche|trouve)(?:[- ]moi)?\s+(?:des |les |une |la )?"
    r"(?:images?|photos?)\s+(?:de |d'|du |des )(.+?)\s*\??$")

# ── notes à la voix : lire les dernières, tout effacer (phrase complète exigée)
RE_NOTES_SHOW = re.compile(
    r"^(?:montre|affiche|lis|donne)(?:[- ]moi)?\s+(?:mes|les)\s+"
    r"(?:\d+\s+)?(?:dernieres\s+)?notes$")
RE_NOTES_CLEAR = re.compile(r"^(?:supprime|efface) toutes (?:mes|les) notes$")

# ── « où est X » / restaurants (version cartes) — filtres anti-faux-positifs
RE_WHEREIS = re.compile(r"^ou (?:est|se trouve|se situe)\s+(.+?)\s*\??$")
_WHEREIS_SKIP = re.compile(
    r"\b(?:image|photo|restaurant|meteo|mail|note|fichier|dossier|minuteur"
    r"|fenetre|curseur|souris)\b|^(?:un|une)\s")
RE_RESTO = re.compile(
    r"^(?:trouve|cherche)(?:[- ]moi)?\s+(?:un |des )?restaurants?\b\s*(.*)$"
    r"|^ou manger\b\s*(.*)$")

# ── YouTube API (JARVIS) : recherche multi + choix vocal, résumé, tendances
RE_YT_SEARCH = re.compile(
    r"^(?:cherche|recherche|trouve)(?:[- ]moi)?\s+(.+?)\s+sur\s+youtube\s*$")
RE_YT_RESUME = re.compile(
    r"^resume(?:[- ]moi)? (?:cette |la )?video(?:\s+(.+))?$")
RE_YT_TREND = re.compile(
    r"^(?:les )?tendances(?: youtube)?(?:\s+(musique|gaming|sport|film|tech|actu|humour))?$"
    r"|^quoi de (?:nouveau|populaire) sur youtube$")
RE_YT_CHANNEL = re.compile(
    r"^(?:infos?|parle[- ]moi) (?:sur |de |de la |du )?(?:la )?chaine (.+)$")
RE_YT_LAST = re.compile(
    r"^(?:les )?dernieres videos (?:de |de la |du )(?:la chaine )?(.+)$")
PENDING_CHOICE = {"items": [], "t": 0.0}
_ORDINAUX = {"premier": 0, "premiere": 0, "deuxieme": 1, "seconde": 1,
             "troisieme": 2, "quatrieme": 3, "cinquieme": 4,
             "dernier": -1, "derniere": -1}
RE_CHOICE = re.compile(
    r"^(?:mets?|joue|lance|ouvre)?\s*(?:le |la )?"
    r"(premiere?|deuxieme|seconde|troisieme|quatrieme|cinquieme|derniere?"
    r"|numero \d+|\d+)\s*$")

# ── sport (TheSportsDB via webinfo) — « classement » AVANT « résultats »
RE_SPORT_TABLE = re.compile(r"^classement (?:de la |de l'|du |de )?(.+)$")
RE_SPORT_RES = re.compile(
    r"^(?:resultats?|scores?|derniers matchs?) (?:du |de la |de l'|des |de )(.+)$")
RE_SPORT_NEXT = re.compile(
    r"^(?:prochain match|quand joue) (?:du |de la |de l'|des |de )?(.+?)\s*\??$")

# ── IPTV : « mets la télé », « zappe sur TF1 »
RE_IPTV = re.compile(
    r"^(?:mets?|lance|ouvre|allume) (?:la )?(?:tele|tv|television)"
    r"(?:\s+sur\s+(.+))?$|^zappe (?:sur |vers )?(.+)$|^chaine (.+)$")

# ── Obsidian (le mot « obsidian » est obligatoire : zéro conflit notes)
RE_OBS_CREATE = re.compile(
    r"^(?:cree|nouvelle) (?:une )?note obsidian (?:appelee |nommee )?(.+?)"
    r"(?:\s+avec\s+(.+))?$")
RE_OBS_READ = re.compile(r"^lis (?:la |ma )?note obsidian (.+)$")
RE_OBS_DEL = re.compile(r"^supprime (?:la |ma )?note obsidian (.+)$")
RE_OBS_LIST = re.compile(r"^(?:liste|montre) (?:mes )?notes obsidian$")
RE_OBS_SEARCH = re.compile(
    r"^cherche (.+?) dans (?:mes notes )?obsidian$")

# ── désinstallation (le désinstallateur OFFICIEL s'ouvre et demande
#    lui-même confirmation — jamais de suppression silencieuse)
RE_UNINSTALL = re.compile(r"^desinstalle[rz]?\s+(.+)$")
RE_PROGRAMS = re.compile(
    r"^(?:montre|liste|affiche) (?:les |mes )?programmes(?: installes)?$")

# ── webcam (vision) : déclencheurs explicites — « qu'est-ce que tu vois »
#    reste l'ÉCRAN (RE_SCREEN)
RE_CAMERA = re.compile(
    r"\bwebcam\b|^regarde[- ]moi$|^(?:comment est|regarde) ma tenue$"
    r"|^qu'est[- ]ce que je tiens(?: dans (?:la|ma) main)?\s*\??$"
    r"|^prends?[- ]moi en photo$|par la camera\b")

# ── écrire dans un champ par vision : « écris bonjour dans le champ de recherche »
RE_VISION_WRITE = re.compile(
    r"^ecris\s+(.+?)\s+dans\s+(?:le champ|la barre|la zone)"
    r"(?:\s+de recherche)?(?:\s+(?:de |du |d')?(.+))?$")

# ── rappel local d'un fait mémorisé (hors-ligne, sans IA)
RE_RECALL = re.compile(
    r"^(?:comment s'appelle|quel est le nom de|c'est quoi|quelle est|quel est)"
    r"\s+(?:mon|ma|mes)\s+(.+?)\s*\??$")

# ── aide vocale : « que peux-tu faire ? » (variantes fautes ASR incluses)
_HELP_PHRASES = {
    "que peux-tu faire", "que peux tu faire", "qu'est-ce que tu sais faire",
    "que sais-tu faire", "que sais tu faire", "tu sais faire quoi",
    "tu peux faire quoi", "tu peut faire quoi", "aide", "aide-moi",
    "liste des commandes", "quelles sont tes commandes",
    "c'est quoi tes commandes", "montre-moi ce que tu sais faire",
}

# ── small-talk (matchs EXACTS uniquement — jamais de sous-chaîne)
_ST_HELLO = {"salut", "coucou", "hello", "hey", "yo", "bonsoir", "salut nova",
             "coucou nova", "hello nova", "bonsoir nova"}
_ST_CAVA = {"ca va", "ca va ?", "comment ca va", "comment vas-tu",
            "comment vas tu", "tu vas bien", "la forme"}
_ST_WHO = {"qui es-tu", "qui es tu", "tu es qui", "t'es qui",
           "comment tu t'appelles", "comment t'appelles-tu",
           "quel age as-tu", "quel age tu as", "tu as quel age",
           "presente-toi", "presente toi"}
_ST_LOVE = {"bravo", "bien joue", "t'es le meilleur", "tu es le meilleur",
            "t'es la meilleure", "je t'aime", "tu es genial", "t'es genial",
            "tu es geniale", "bien joue nova", "bravo nova"}


# --- ouverture vocale instantanée (sans IA) : sites web et applis Windows ---

SITES = {
    "youtube": "https://www.youtube.com", "youtube music": "https://music.youtube.com",
    "gmail": "https://mail.google.com", "mail": "https://mail.google.com",
    "mails": "https://mail.google.com", "google": "https://www.google.com",
    "maps": "https://maps.google.com", "google maps": "https://maps.google.com",
    "whatsapp": "https://web.whatsapp.com", "notion": "https://www.notion.so",
    "spotify": "https://open.spotify.com", "deezer": "https://www.deezer.com",
    "netflix": "https://www.netflix.com", "prime video": "https://www.primevideo.com",
    "disney plus": "https://www.disneyplus.com", "twitch": "https://www.twitch.tv",
    "molotov": "https://www.molotov.tv", "arte": "https://www.arte.tv",
    "discord": "https://discord.com/app", "slack": "https://app.slack.com",
    "teams": "https://teams.microsoft.com", "zoom": "https://zoom.us/join",
    "instagram": "https://www.instagram.com", "tiktok": "https://www.tiktok.com",
    "twitter": "https://x.com", "x": "https://x.com",
    "facebook": "https://www.facebook.com", "messenger": "https://www.messenger.com",
    "linkedin": "https://www.linkedin.com", "reddit": "https://www.reddit.com",
    "pinterest": "https://www.pinterest.fr", "snapchat": "https://web.snapchat.com",
    "amazon": "https://www.amazon.fr", "leboncoin": "https://www.leboncoin.fr",
    "vinted": "https://www.vinted.fr", "ebay": "https://www.ebay.fr",
    "github": "https://github.com", "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai", "gemini": "https://gemini.google.com",
    "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
    "google docs": "https://docs.google.com", "google sheets": "https://sheets.google.com",
    "onedrive": "https://onedrive.live.com", "outlook": "https://outlook.live.com",
    "agenda": "https://calendar.google.com", "google agenda": "https://calendar.google.com",
    "canva": "https://www.canva.com", "figma": "https://www.figma.com",
    "wikipedia": "https://fr.wikipedia.org", "traducteur": "https://translate.google.com",
    "google traduction": "https://translate.google.com",
    "meteo france": "https://meteofrance.com", "france info": "https://www.franceinfo.fr",
    "le monde": "https://www.lemonde.fr", "l'equipe": "https://www.lequipe.fr",
    "paypal": "https://www.paypal.com", "booking": "https://www.booking.com",
    "nouveau document": "https://docs.new", "nouveau doc": "https://docs.new",
    "nouveau tableur": "https://sheets.new", "nouvelle feuille": "https://sheets.new",
    "nouvelle presentation": "https://slides.new", "nouveau formulaire": "https://forms.new",
    "airbnb": "https://www.airbnb.fr", "uber": "https://m.uber.com",
    "uber eats": "https://www.ubereats.com", "deliveroo": "https://deliveroo.fr",
    "doctolib": "https://www.doctolib.fr", "ameli": "https://www.ameli.fr",
    "impots": "https://www.impots.gouv.fr", "sncf": "https://www.sncf-connect.com",
}

APPS = {
    "bloc-notes": "notepad", "bloc notes": "notepad", "notepad": "notepad",
    "calculatrice": "calc", "explorateur": "explorer",
    "explorateur de fichiers": "explorer", "paint": "mspaint",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "parametres": "ms-settings:", "reglages windows": "ms-settings:",
    "gestionnaire des taches": "taskmgr", "terminal": "wt",
    "invite de commandes": "cmd", "panneau de configuration": "control",
    "corbeille": "shell:RecycleBinFolder",
    "horloge": "ms-clock:", "reveil": "ms-clock:", "photos": "ms-photos:",
    "magasin": "ms-windows-store:", "microsoft store": "ms-windows-store:",
    # navigateurs et applis de bureau : « google chrome » = l'APPLICATION,
    # pas une recherche google (résolus via les App Paths de Windows)
    "chrome": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "mozilla firefox": "firefox",
    "edge": "msedge", "microsoft edge": "msedge",
    "opera": "opera", "brave": "brave",
    "vlc": "vlc", "steam": "steam",
    # catalogue étendu (JARVIS) — résolus par winext.resolve_exe (registre)
    "discord": "discord",
    "teams": "ms-teams:", "microsoft teams": "ms-teams:",
    "telegram": "telegram",
    "zoom": "zoom",
    "vs code": "code", "visual studio code": "code", "vscode": "code",
    "obs": "obs64", "obs studio": "obs64",
    "blender": "blender", "gimp": "gimp",
    "photoshop": "photoshop", "illustrator": "illustrator",
    "premiere pro": "premiere pro", "after effects": "afterfx",
    "epic games": "com.epicgames.launcher:",
    "minecraft": "minecraftlauncher",
    "sept zip": "7zFM", "7-zip": "7zFM", "winrar": "winrar",
    "outlook": "outlook",
    "outil de capture": "SnippingTool",
    "enregistreur vocal": "ms-soundrecorder:", "magnetophone": "ms-soundrecorder:",
    "table des caracteres": "charmap",
    "nettoyage de disque": "cleanmgr",
    "informations systeme": "msinfo32",
    "moniteur de ressources": "resmon",
}

RE_OPEN = re.compile(
    r"^(?:ouvres?|ouvrir|va sur|vas sur|aller sur|lances?|lancer|affiches?"
    r"|afficher|montres?|montrer|demarres?|demarrer)(?:[- ]moi)?\s+(.+)$")
_OPEN_ARTICLES = ("le ", "la ", "les ", "l'", "mon ", "ma ", "mes ",
                  "un ", "une ", "du ", "sur ")

# pages profondes des Paramètres Windows : « ouvre les paramètres de l'écran »
# doit ouvrir la page Affichage, pas juste l'application Paramètres
SETTINGS_PAGES = {
    "ecran": "ms-settings:display", "affichage": "ms-settings:display",
    "luminosite": "ms-settings:display", "son": "ms-settings:sound",
    "volume": "ms-settings:sound", "audio": "ms-settings:sound",
    "micro": "ms-settings:sound", "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi", "wi-fi": "ms-settings:network-wifi",
    "reseau": "ms-settings:network", "internet": "ms-settings:network",
    "batterie": "ms-settings:batterysaver", "stockage": "ms-settings:storagesense",
    "applications": "ms-settings:appsfeatures", "confidentialite": "ms-settings:privacy",
    "comptes": "ms-settings:accounts", "heure": "ms-settings:dateandtime",
    "date": "ms-settings:dateandtime", "langue": "ms-settings:regionlanguage",
    "clavier": "ms-settings:typing", "souris": "ms-settings:mousetouchpad",
    "pave tactile": "ms-settings:devices-touchpad",
    "notifications": "ms-settings:notifications",
    "personnalisation": "ms-settings:personalization",
    "fond d'ecran": "ms-settings:personalization-background",
    "couleurs": "ms-settings:colors", "themes": "ms-settings:themes",
    "barre des taches": "ms-settings:taskbar",
    "eclairage nocturne": "ms-settings:nightlight",
    "mode nuit": "ms-settings:nightlight",
    "mise a jour": "ms-settings:windowsupdate",
    "mises a jour": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "imprimante": "ms-settings:printers", "imprimantes": "ms-settings:printers",
    "camera": "ms-settings:camera",
}

RE_SETTINGS = re.compile(
    r"^(?:parametres?|reglages?)(?:\s+windows)?(?:\s+(?:de|du|des|d'|pour))?\s*(.*)$")

# raccourcis clavier à la voix : correspondance EXACTE (pas de faux positifs)
SHORTCUTS_VOICE = {
    "colle": ("ctrl+v", "Collé"),
    "copie": ("ctrl+c", "Copié"),
    "coupe": ("ctrl+x", "Coupé"),
    "annule": ("ctrl+z", "Annulé"),
    "retablis": ("ctrl+y", "Rétabli"),
    "refais": ("ctrl+y", "Rétabli"),
    "selectionne tout": ("ctrl+a", "Tout sélectionné"),
    "enregistre": ("ctrl+s", "Enregistré"),
    "plein ecran": ("f11", "Plein écran"),
    "ferme la fenetre": ("alt+f4", "Fenêtre fermée"),
    "ferme l'onglet": ("ctrl+w", "Onglet fermé"),
    "nouvel onglet": ("ctrl+t", "Nouvel onglet"),
    "rouvre l'onglet": ("ctrl+shift+t", "Onglet rouvert"),
    "onglet suivant": ("ctrl+tab", "Onglet suivant"),
    "onglet precedent": ("ctrl+shift+tab", "Onglet précédent"),
    "actualise": ("f5", "Actualisé"),
    "rafraichis": ("f5", "Actualisé"),
    "montre le bureau": ("win+d", "Bureau affiché"),
    "affiche le bureau": ("win+d", "Bureau affiché"),
    "verrouille": ("win+l", "Verrouillé"),
    "verrouille le pc": ("win+l", "Verrouillé"),
    "verrouille l'ecran": ("win+l", "Verrouillé"),
    "capture d'ecran": ("win+shift+s", "À toi de découper"),
    "fais une capture": ("win+shift+s", "À toi de découper"),
    "ouvre les emojis": ("win+.", "Emojis"),
}


def _fuzzy_key(name, mapping):
    """Tolère les fautes de transcription : « youtub » → « youtube »."""
    import difflib
    m = difflib.get_close_matches(name, list(mapping), n=1, cutoff=0.75)
    return m[0] if m else None


def resolve_open(n):
    """« ouvre notion », « lance word » → ('url'|'app', cible, nom). None sinon."""
    m = RE_OPEN.match(n)
    if not m:
        return None
    name = m.group(1).strip(" .!?")
    # applis définies par l'utilisateur (Réglages > Système) : prioritaires,
    # testées AVANT le retrait d'article (« ouvre mon site » garde son « mon »)
    custom = {core.normalize(k).strip(): str(v)
              for k, v in (core.CFG.get("custom_apps") or {}).items() if k}

    def _custom_hit(key):
        t = custom.get(key)
        if t is None:
            return None
        return ("url" if t.lower().startswith(("http://", "https://")) else "app",
                t, key)

    hit = _custom_hit(name)
    if hit:
        return hit
    for art in _OPEN_ARTICLES:
        if name.startswith(art):
            name = name[len(art):].strip()
            break
    hit = _custom_hit(name)
    if hit:
        return hit
    if name in APPS:
        return ("app", APPS[name], name)
    if name in SITES:
        return ("url", SITES[name], name)
    # dossiers Windows : « ouvre mes téléchargements », « ouvre le bureau »
    folder = files_mode.resolve_folder(name)
    if folder:
        return ("app", folder, name)
    ms = RE_SETTINGS.match(name)
    if ms:
        key = ms.group(1).strip(" .!?")
        for art in ("le ", "la ", "les ", "l'", "de l'", "de la ", "du "):
            if key.startswith(art):
                key = key[len(art):].strip()
                break
        if key in SETTINGS_PAGES:
            return ("app", SETTINGS_PAGES[key], f"les paramètres ({key})")
        if not key:
            return ("app", "ms-settings:", "les paramètres")
    # URL, domaine ou IP dictés : « ouvre lemonde.fr », « va sur localhost:8123 »
    dom = name.replace(" ", "")
    if re.fullmatch(r"(?:localhost|(?:\d{1,3}\.){3}\d{1,3})(?::\d+)?(?:/\S*)?", dom):
        return ("url", "http://" + dom, name)
    if re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.(?:fr|com|net|org|io|dev|app|tv|co"
                    r"|eu|be|ch|ca|info|gouv\.fr)(?:/\S*)?", dom):
        return ("url", "https://" + dom, name)
    # dernier recours : faute de transcription (« youtub », « spotifi »)
    fz = _fuzzy_key(name, APPS) or _fuzzy_key(name, SITES)
    if fz:
        target = APPS.get(fz) or SITES[fz]
        return ("app" if fz in APPS else "url", target, fz)
    return None


def active_profile():
    pid = core.CFG.get("active_profile") or storage.ensure_default_profile()
    return storage.get_profile(pid) or storage.get_profile(storage.ensure_default_profile())


def find_contact(name):
    p = active_profile()
    if not p or not name:
        return None
    q = core.normalize(name).strip()
    for c in p.get("contacts", []):
        n = core.normalize(c.get("name", ""))
        if n and (n == q or n in q or q in n):
            return c
    return None


# ------------------------------------------------------------- domotique ----

def _ha_entity(name, kinds):
    """Trouve l'entité HA dont le nom vocal correspond (kinds = types acceptés).
    Retourne (entity_id, nom) ou (None, None)."""
    ents = core.CFG.get("ha_entities") or {}
    q = core.normalize(name or "").strip()
    # correspondance exacte puis approximative sur le bon type
    cands = {core.normalize(k): (k, v) for k, v in ents.items()
             if isinstance(v, dict) and v.get("type") in kinds and v.get("id")}
    if not cands:
        return None, None
    if q in cands:
        k, v = cands[q]
        return v["id"], k
    for nk, (k, v) in cands.items():
        if q and (q in nk or nk in q):
            return v["id"], k
    # une seule entité du bon type + demande vague (« la lumière ») → elle
    if len(cands) == 1 and (not q or "lumiere" in q or "lampe" in q):
        k, v = next(iter(cands.values()))
        return v["id"], k
    return None, None


# extensions domotiques JARVIS : scènes, thermostat, verrou, alarme, aspirateur
RE_SCENE = re.compile(
    r"^(?:active|lance|mets?) (?:la |l')?(?:scene|ambiance)\s+(.+)$")
RE_ALL_LIGHTS = re.compile(r"^(allume|eteins) toutes les lumieres$")
RE_LIGHT_TOGGLE = re.compile(
    r"^bascule (?:la lumiere|les lumieres|la lampe)"
    r"(?:\s+(?:du |de la |de l')?(.*))?$")
RE_THERMOSTAT = re.compile(
    r"^(?:mets?|regle) (?:le )?(?:chauffage|thermostat|la temperature)"
    r"(?:\s+(?:du |de la |de l')?(.*?))?\s+(?:a|sur)\s+(\d{1,2})\s*(?:degres?)?$")
RE_LOCK = re.compile(
    r"^(verrouille|deverrouille) (?:la |le )?(?:porte|serrure|verrou)"
    r"(?:\s+(?:d'entree|du |de la |de l')?\s*(.*))?$")
RE_ALARM = re.compile(r"^(active|desactive) l[' ]alarme$")
RE_VACUUM = re.compile(
    r"^(?:lance|demarre|arrete|stoppe|mets? en pause) (?:l')?aspirateur$"
    r"|^(?:renvoie|ramene) (?:l')?aspirateur (?:a sa |a la )?base$")
RE_HA_BATT = re.compile(
    r"^(?:quelle est la |combien de |niveau de )?batterie (?:du |de la |de l')(.+?)\s*\??$")
RE_HA_HUMID = re.compile(
    r"^(?:quelle est l'|quel est le taux d')?humidite"
    r"\s*(?:dans (?:le |la |l')?|du |de la |de l')?(.*?)\s*\??$")


def _classify_home(n):
    # thermostat AVANT la luminosité (« mets le chauffage à 20 » ≠ lumière)
    m = RE_THERMOSTAT.match(n)
    if m and 5 <= int(m.group(2)) <= 30:
        eid, nm = _ha_entity(m.group(1) or "", ("climate",))
        if eid:
            return ("home", "clim:" + eid, m.group(2))
    m = RE_SCENE.match(n)
    if m:
        eid, nm = _ha_entity(m.group(1), ("scene",))
        if eid:
            return ("home", "scene:" + eid, nm)
    m = RE_ALL_LIGHTS.match(n)
    if m:
        return ("home", "all_on" if m.group(1) == "allume" else "all_off", "")
    m = RE_LIGHT_TOGGLE.match(n)
    if m:
        eid, nm = _ha_entity(m.group(1) or "", ("light", "switch"))
        if eid:
            return ("home", "toggle:" + eid, nm)
    m = RE_LOCK.match(n)
    if m:
        eid, nm = _ha_entity(m.group(2) or "porte", ("lock",))
        if eid:
            lock = m.group(1) == "verrouille"
            return ("home", ("lock:" if lock else "unlock:") + eid, nm)
    m = RE_ALARM.match(n)
    if m:
        eid, nm = _ha_entity("alarme", ("alarm",))
        if eid:
            return ("home", ("alarm_on:" if m.group(1) == "active" else "alarm_off:") + eid, nm)
    if RE_VACUUM.match(n):
        eid, nm = _ha_entity("aspirateur", ("vacuum",))
        if eid:
            if "base" in n:
                act = "dock"
            elif "pause" in n:
                act = "pause"
            elif n.startswith(("arrete", "stoppe")):
                act = "stop"
            else:
                act = "start"
            return ("home", f"vac:{act}:" + eid, nm)
    m = RE_HA_BATT.match(n)
    if m:
        eid, nm = _ha_entity(m.group(1), ("battery", "sensor"))
        if eid:
            return ("home", "read:" + eid, nm)
    m = RE_HA_HUMID.match(n)
    if m:
        eid, nm = _ha_entity(m.group(1) or "humidite", ("sensor",))
        if eid and ("humid" in core.normalize(nm or "") or m.group(1)):
            return ("home", "read:" + eid, nm)
    m = RE_LIGHT_COLOR.match(n)
    if m and m.group(2) in COULEURS_RGB:
        eid, nm = _ha_entity(m.group(1), ("light",))
        if eid:
            return ("home", "color:" + eid, m.group(2))
    m = RE_LIGHT_PCT.match(n)
    if m:
        eid, nm = _ha_entity(m.group(1), ("light",))
        if eid:
            return ("home", "bright:" + eid, m.group(2))
    m = RE_PLUG.match(n)
    if m:
        eid, nm = _ha_entity(m.group(2), ("switch",))
        if eid:
            on = m.group(1) in ("allume", "active", "branche")
            return ("home", ("plugon:" if on else "plugoff:") + eid, nm)
    m = RE_LIGHT_ON.match(n)
    if m and ("lumiere" in n or "lampe" in n or "allume" in n):
        eid, nm = _ha_entity(m.group(1), ("light",))
        if eid:
            return ("home", "on:" + eid, nm)
    m = RE_LIGHT_OFF.match(n)
    if m and ("lumiere" in n or "lampe" in n):
        eid, nm = _ha_entity(m.group(1), ("light",))
        if eid:
            return ("home", "off:" + eid, nm)
    m = RE_TEMP.match(n)
    if m:
        eid, nm = _ha_entity(m.group(1), ("sensor",))
        if eid:
            return ("home", "temp:" + eid, nm)
    return None


# mise en veille (JARVIS « sleep words ») : phrase ENTIÈRE uniquement —
# « merci de fermer chrome » ne doit jamais matcher
RE_DISMISS = re.compile(
    r"^(?:merci(?: beaucoup| bien| nova)?|c'?est (?:tout|bon|parfait)|ce sera tout"
    r"|rien(?: du tout)?|non merci|laisse tomber|repos|au revoir"
    r"|bonne (?:nuit|soiree|journee)|stop|tais[- ]toi|silence|chut)$")


# ------------------------------------------------------------ classifieur ---

def _classify_pc(n):
    """Contrôle du PC : alimentation (veille/annuler/confirmer/redémarrer/arrêt
    avec délai), désinstallation de programme, antivirus Defender, écriture par
    vision (« écris X dans le champ Y »). (…) ou None."""
    # alimentation du PC (veille / arrêt / redémarrage, avec confirmation)
    if RE_POWER_SLEEP.match(n):
        return ("power", "sleep", "")
    if RE_POWER_CANCEL.match(n):
        return ("power", "cancel", "")
    if RE_POWER_CONFIRM.match(n):
        return ("power", "off_do", "")
    if RE_POWER_REBOOT.match(n):
        return ("power", "reboot", "")
    m = RE_POWER_OFF.match(n)
    if m:
        delay = (m.group(1) or "").strip()
        if delay and timers.parse_duration(delay):
            return ("power", f"off:{timers.parse_duration(delay)}", delay)
        return ("power", "off_ask", "")

    # désinstallation : le désinstallateur OFFICIEL s'ouvre (il confirme lui-même)
    m = RE_UNINSTALL.match(n)
    if m:
        return ("uninstall", m.group(1).strip(" .!?"), "")
    if RE_PROGRAMS.match(n):
        return ("uninstall", "@list", "")

    # antivirus Windows Defender (phrase explicite)
    if RE_AV.match(n):
        return ("antivirus", "", "")

    # écriture par vision : « écris bonjour dans le champ de recherche »
    # (traitée dans app.py — capture + localisation + clic + frappe)
    m = RE_VISION_WRITE.match(n)
    if m:
        return ("visionwrite", (m.group(2) or "le champ de recherche").strip(),
                m.group(1).strip())
    return None


def _classify_memory(n):
    """Mémoire durable : retenir un fait (ou un rappel si vraie unité de temps),
    oublier un fait / rétracter, rappel local hors-ligne d'un fait mémorisé
    (« c'est quoi ma plaque ? »). (…) ou None."""
    # mémoire longue : retenir / oublier un fait durable
    m = RE_REMEMBER.match(n)
    if m:
        content = m.group(1).strip(" ,.")
        # « souviens-toi de sortir les pâtes dans 10 minutes » = un RAPPEL,
        # mais seulement avec une vraie unité de temps (« dans le bâtiment 7 »
        # reste un fait : le repli nombre-seul de parse_duration piège)
        if " dans " in content:
            task, _, dur = content.rpartition(" dans ")
            if re.search(r"\b(?:h|heures?|min|mn|minutes?|s|sec|secondes?)\b"
                         r"|quart d'heure|demi[- ]?heure", dur) \
                    and timers.parse_duration(dur):
                return ("timer", dur, task.strip(" ,."))
        return ("memory", "remember", content)
    m = RE_FORGET.match(n)
    if m and not RE_TIMER_WORD.search(m.group(1)) \
            and not RE_TIMER_CANCEL.match(n):
        what = m.group(1).strip(" ,.")
        if what in ("ca", "cela", "tout", "ce que j'ai dit",
                    "ce que je viens de dire", "ma derniere phrase"):
            # rétractation de conversation, pas une suppression de fait
            return ("memory", "dismiss", "")
        return ("memory", "forget", what)

    # rappel local d'un fait (« c'est quoi ma plaque ? ») : hors-ligne,
    # sans IA — seulement si un fait correspond vraiment
    m = RE_RECALL.match(n)
    if m:
        words = [w for w in m.group(1).split() if len(w) > 3]
        if words:
            try:
                for f in storage.list_facts(60):
                    fn = core.normalize(f["fact"])
                    if any(w in fn for w in words):
                        return ("recall", f["fact"], "")
            except Exception:
                pass
    return None


def _classify_messaging(n):
    """Appels, messages (à un contact, dictée, libre), webcam, puis « où est X »
    et restaurants (filtres anti-faux-positifs JARVIS). (…) ou None."""
    m = RE_CALL.match(n)
    if m:
        return ("call", m.group(1).strip(), "")

    m = RE_MSG_TO.match(n)
    if m:
        return ("message", m.group(1).strip(), m.group(2).strip())
    m = RE_MSG_DIS.match(n)
    if m:
        return ("message", m.group(1).strip(), m.group(2).strip())
    m = RE_MSG_FREE.match(n)
    if m:
        return ("message", "", m.group(1).strip())

    # webcam (vision) : déclencheurs explicites — traité dans app.py
    if RE_CAMERA.search(n):
        return ("camera", "", "")

    # « où est X » / restaurants → cartes (filtres anti-faux-positifs JARVIS)
    m = RE_WHEREIS.match(n)
    if m and not _WHEREIS_SKIP.search(m.group(1)):
        return ("whereis", m.group(1).strip(), "")
    if n in ("d'autres restaurants", "d autres restaurants",
             "autres restaurants", "encore des restaurants"):
        return ("resto", "@more", "")
    m = RE_RESTO.match(n)
    if m:
        place = (m.group(1) or m.group(2) or "").strip(" .!?")
        place = re.sub(r"^(?:a|à|au|aux|pres de|proche de|autour de)\s+", "", place)
        if place in ("moi", "ici", "proximite", "cote", "de moi", "pres"):
            place = ""
        return ("resto", place, "")
    return None


def _classify_media_audio(n):
    """Musique et audio, dans l'ordre : playlist attitrée (« mets de la
    musique »), titre nommé, contexte Spotify (playlist/album/artiste), genre
    sans service, itinéraire, volume (système/relatif/par appli/mute), fenêtres
    (côte à côte, bascule), puis commandes média génériques. (…) ou None."""
    # « mets de la musique » (sans titre précis) → playlist attitrée.
    # AVANT RE_MUSIC ; « mets LA musique » sans « de » reste une reprise média
    if re.match(r"^(?:mets?|joue|lance|mets moi|met moi)"
                r"\s+(?:de la|un peu de|du son|de la bonne)"
                r"\s+musique(?:\s+sur\s+(youtube|spotify))?$", n) \
            or re.match(r"^(?:joue|lance)\s+(?:ma|une)\s+(?:musique|playlist)"
                        r"(?:\s+sur\s+(youtube|spotify))?$", n):
        svc = "youtube" if "youtube" in n else "spotify"
        return ("music_default", svc, "")

    m = RE_MUSIC.match(n)
    if m:
        return ("music", m.group(1).strip(), m.group(2).strip())

    # playlist / album / artiste nommés (Spotify contexte, JARVIS)
    m = re.match(r"^(?:joue|mets?|lance) (?:la |ma )?playlist\s+(.+)$", n)
    if m:
        return ("spotify_ctx", "playlist", m.group(1).strip(" .!?"))
    m = re.match(r"^(?:joue|mets?|lance) l'album\s+(.+)$", n)
    if m:
        return ("spotify_ctx", "album", m.group(1).strip(" .!?"))
    m = re.match(r"^(?:joue|mets?|lance) l'artiste\s+(.+)$", n)
    if m:
        return ("spotify_ctx", "artist", m.group(1).strip(" .!?"))

    # « joue du jazz » : genre/artiste sans service nommé (JARVIS)
    m = RE_MUSIC_NOSVC.match(n)
    if m:
        q = m.group(1).strip(" .!?")
        if q not in ("musique", "son", "chanson", "lecture", "la musique",
                     "bonne musique", "zik", "bruit"):
            svc = "spotify" if integrations.spotify_connected() else "youtube"
            return ("music", q, svc)

    m = RE_NAVIGATION.match(n)
    if m and m.group(1) and not m.group(1).strip().startswith("sur ") \
            and "fenetre" not in m.group(1):
        # « va sur … » = un site, « va vers la fenêtre … » = bascule de fenêtre
        # (gérés ailleurs), pas un itinéraire Google Maps
        return ("navigation", m.group(1).strip(), "")

    # volume précis et son par appli — AVANT les règles média génériques
    m = RE_VOL_SET.match(n) or RE_VOL_BARE.match(n)
    if m:
        return ("volume", "set", m.group(1))
    m = RE_VOL_REL.match(n)
    if m:
        sign = "-" if m.group(1).startswith(("baisse", "diminue", "descend")) else "+"
        return ("volume", "rel", sign + m.group(2))
    # volume d'UNE application : « monte le son de spotify (de 30) » (JARVIS)
    m = re.match(r"^(monte|augmente|baisse|diminue) le (?:son|volume)"
                 r" (?:de |du |d')(.+?)(?:\s+de\s+(\d{1,3}))?\s*%?$", n)
    if m and not m.group(2).strip().isdigit():
        sign = "-" if m.group(1).startswith(("baisse", "diminue")) else "+"
        amt = m.group(3) or "20"
        return ("volume", "app", f"{sign}{amt}|{m.group(2).strip()}")
    m = RE_APP_MUTE.match(n)
    if m:
        mute = m.group(1).startswith("coupe")
        return ("volume", "mute_app" if mute else "unmute_app", m.group(2).strip())

    # fenêtres : basculer / côte à côte
    m = RE_WIN_SPLIT.match(n)
    if m:
        return ("window", "split", m.group(1).strip() + "||" + m.group(2).strip())
    m = RE_WIN_FOCUS.match(n) or RE_WIN_FOCUS2.match(n)
    if m and not m.group(1).strip().startswith("sur "):
        return ("window", "focus", m.group(1).strip())

    for rx, action in MEDIA_ACTIONS:
        mm = rx.search(n)
        if mm:
            # la commande média doit couvrir TOUTE la phrase (politesse et
            # articles tolérés) ; enfouie dans une demande plus riche
            # (« baisse le son dès que… et ouvre… ») → IA planificatrice
            leftover = (n[:mm.start()] + " " + n[mm.end():]).strip(" ,.!?")
            extra = [w for w in leftover.split() if w not in _MEDIA_GLUE]
            if len(extra) <= 1:
                return ("media", action, "")
            break
    return None


def _classify_youtube_sport(n):
    """YouTube Data (recherche + choix vocal, résumé, tendances, chaînes) puis
    sport (classement AVANT résultats, prochain match). (…) ou None."""
    # YouTube API : recherche avec choix vocal, résumé, tendances, chaînes
    m = RE_YT_SEARCH.match(n)
    if m:
        return ("youtube", "search", m.group(1).strip())
    m = RE_YT_RESUME.match(n)
    if m:
        return ("youtube", "resume", (m.group(1) or "").strip())
    m = RE_YT_TREND.match(n)
    if m:
        return ("youtube", "trend", m.group(1) or "")
    m = RE_YT_CHANNEL.match(n)
    if m:
        return ("youtube", "channel", m.group(1).strip(" .!?"))
    m = RE_YT_LAST.match(n)
    if m:
        return ("youtube", "last", m.group(1).strip(" .!?"))

    # sport : classement AVANT résultats (« classement de la ligue 1 »)
    m = RE_SPORT_TABLE.match(n)
    if m:
        return ("sport", "table", m.group(1).strip(" .!?"))
    m = RE_SPORT_RES.match(n)
    if m:
        return ("sport", "res", m.group(1).strip(" .!?"))
    m = RE_SPORT_NEXT.match(n)
    if m:
        return ("sport", "next", m.group(1).strip(" .!?"))
    return None


def _classify_obsidian_notes(n):
    """Obsidian (mot « obsidian » obligatoire) : créer, lire, supprimer, lister,
    chercher ; plus les notes vocales : lire les dernières, tout effacer.
    (…) ou None."""
    # Obsidian (le mot « obsidian » est obligatoire dans la phrase)
    m = RE_OBS_CREATE.match(n)
    if m:
        return ("obsidian", "create:" + m.group(1).strip(),
                (m.group(2) or "").strip())
    m = RE_OBS_READ.match(n)
    if m:
        return ("obsidian", "read:" + m.group(1).strip(" .!?"), "")
    m = RE_OBS_DEL.match(n)
    if m:
        return ("obsidian", "del:" + m.group(1).strip(" .!?"), "")
    if RE_OBS_LIST.match(n):
        return ("obsidian", "list", "")
    m = RE_OBS_SEARCH.match(n)
    if m:
        return ("obsidian", "search:" + m.group(1).strip(), "")

    # notes à la voix : lire les dernières / tout effacer (phrase complète)
    if RE_NOTES_SHOW.match(n):
        return ("notes_voice", "show", "")
    if RE_NOTES_CLEAR.match(n):
        return ("notes_voice", "clear", "")
    return None


def _classify_files(n):
    """Fichiers et listes vocales : tri (par type/date), création de dossier,
    mosaïque, recherche, listes de courses/tâches, contenu de dossier. Le tri
    et le listing exigent un dossier connu. (…) ou None."""
    # fichiers : trier / chercher un fichier (le tri exige un dossier connu),
    # variantes JARVIS : par date, par type et date, « ce dossier », création
    m = RE_SORT.match(n)
    if m:
        arg = m.group(1).strip()
        by_type_date = bool(re.search(r"\bpar type et (?:par )?date$", arg))
        by_date = bool(re.search(r"\bpar (?:date|annee|mois)$", arg))
        arg = re.sub(r"\s+par type et (?:par )?date$"
                     r"|\s+par (?:date|annee|mois|categorie|type)$", "", arg).strip()
        if arg in ("ce dossier", "le dossier") and LAST_FOLDER["path"]:
            arg = "@last"
        if arg == "@last" or files_mode.resolve_folder(arg):
            kind = "sortdatetype" if by_type_date else \
                ("sortdate" if by_date else "sort")
            return ("files", kind + ":" + arg, "")
    m = RE_MKDIR.match(n)
    if m:
        return ("files", "mkdir:" + m.group(1).strip(" .!?"),
                (m.group(2) or "").strip())
    if RE_QUAD.match(n):
        return ("files", "quad", "")
    m = RE_FIND_FILE.match(n)
    if m:
        return ("files", "find:" + m.group(1).strip(" ?."), "")

    # listes vocales
    m = RE_LIST_ADD.match(n)
    if m:
        lst = "taches" if (m.group(2) or "").replace("â", "a") in \
            ("taches", "a faire", "à faire") else "courses"
        return ("list", "add:" + lst, m.group(1).strip())
    m = RE_LIST_SHOW.match(n)
    if m:
        g = m.group(1) if m.lastindex else ""
        lst = "taches" if (g or "").replace("â", "a") in \
            ("taches", "a faire", "à faire") else "courses"
        return ("list", "show:" + lst, "")
    m = RE_LIST_CLEAR.match(n)
    if m:
        lst = "taches" if (m.group(1) or "") in ("taches", "tâches") else "courses"
        return ("list", "clear:" + lst, "")

    # contenu d'un dossier : « liste mes téléchargements » (APRÈS les listes)
    m = RE_LIST_FOLDER.match(n)
    if m:
        arg = m.group(1).strip(" ?.")
        if arg not in ("liste",) and files_mode.resolve_folder(arg) \
                and arg in files_mode.FOLDERS:
            return ("files", "ls:" + arg, "")
    return None


def _classify_timers(n):
    """Minuteurs et rappels : annulation, heure fixe (JARVIS), ajustement,
    comptage, rappels relatifs « dans X », mot-clé minuteur. (…) ou None."""
    if RE_TIMER_CANCEL.match(n):
        return ("timer_cancel", "", "")

    # rappels à heure FIXE (JARVIS) — AVANT les rappels relatifs « dans X »
    m = RE_REMIND_AT_B.match(n)
    if m:
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        texte = m.group(3).strip(" ,.")
        if 0 <= h <= 23 and 0 <= mn <= 59 and len(texte) > 1:
            daily = bool(re.search(r"tous les jours|chaque jour|quotidien", texte))
            texte = re.sub(r"\s*(?:tous les jours|chaque jour|quotidien(?:nement)?)\s*$",
                           "", texte).strip(" ,.")
            return ("timer_at", f"{h:02d}:{mn:02d}" + ("|d" if daily else ""), texte)
    m = RE_REMIND_AT_A.match(n)
    if m and " dans " not in n:
        texte = m.group(1).strip(" ,.")
        h, mn = int(m.group(2)), int(m.group(3) or 0)
        if 0 <= h <= 23 and 0 <= mn <= 59 and len(texte) > 1:
            daily = bool(m.group(4))
            return ("timer_at", f"{h:02d}:{mn:02d}" + ("|d" if daily else ""), texte)

    # ajustement / comptage — AVANT le mot-clé minuteur générique
    m = RE_TIMER_ADJ_ADD.match(n)
    if m and timers.parse_duration(m.group(1)):
        return ("timer_adjust", "+" + str(timers.parse_duration(m.group(1))), "")
    m = RE_TIMER_ADJ_SUB.match(n)
    if m and timers.parse_duration(m.group(1)):
        return ("timer_adjust", "-" + str(timers.parse_duration(m.group(1))), "")
    if RE_TIMER_COUNT.match(n):
        return ("timer_count", "", "")

    m = RE_REMIND_A.match(n)
    if m:
        return ("timer", m.group(1).strip(), m.group(2).strip())
    m = RE_REMIND_B.match(n)
    if m:
        return ("timer", m.group(2).strip(), m.group(1).strip())
    m = RE_TIMER_WORD.search(n)
    if m:
        tail = n[m.end():].lstrip(" ,")
        for pfx in ("de ", "d'", "sur "):
            if tail.startswith(pfx):
                tail = tail[len(pfx):]
                break
        label = ""
        lm = re.search(r"\bpour (.+)$", tail)
        if lm and not timers.parse_duration(lm.group(1)):
            label = lm.group(1).strip(" ,.!?")
            tail = tail[:lm.start()].strip(" ,")
        # la durée valide l'intention ; sinon (question, statut…) → IA
        src = tail if timers.parse_duration(tail) else n
        if timers.parse_duration(src):
            return ("timer", src, label)
    return None


def _classify_infos(n):
    """Infos locales hors-ligne (JARVIS) : heure d'une ville, heure locale,
    capitales, monnaies, épellation, OTAN, blagues, tirages, mot de passe,
    compte à rebours, calcul, conversions, état système. (mode, …) ou None."""
    # heure dans une autre ville — AVANT l'heure locale
    m = RE_TIME_CITY.match(n)
    if m and m.group(1).strip() in fun_mode.FUSEAUX:
        return ("info", "city_time", m.group(1).strip())

    if RE_TIME.match(n):
        return ("time", "", n)

    # ── infos locales hors-ligne (JARVIS) ──
    m = RE_CAPITALE.match(n)
    if m and fun_mode.capitale(m.group(1)):
        return ("info", "capitale", m.group(1).strip())
    m = RE_MONNAIE.match(n)
    if m and fun_mode.monnaie(m.group(1)):
        return ("info", "monnaie", m.group(1).strip())
    m = RE_SPELL.match(n)
    if m:
        return ("info", "spell", m.group(1).strip())
    m = RE_OTAN.match(n)
    if m:
        return ("info", "otan", m.group(1))
    if RE_JOKE.search(n):
        return ("fun", "blague", "")
    if RE_QUOTE.search(n):
        return ("fun", "citation", "")
    if RE_COIN.match(n):
        return ("info", "coin", "")
    m = RE_DICE.match(n)
    if m:
        return ("info", "dice", m.group(1) or "6")
    m = RE_RANDNUM.match(n)
    if m:
        return ("info", "rand", f"{m.group(1) or 1}|{m.group(2) or 100}")
    m = RE_PASSWORD.match(n)
    if m:
        return ("info", "password", m.group(1) or "16")
    if RE_COUNTDOWN.search(n) and fun_mode.compte_a_rebours(n):
        return ("info", "countdown", n)
    calc = fun_mode.calcule(n)
    if calc:
        return ("info", "calc", calc)
    conv = fun_mode.convertit(n)
    if conv:
        return ("info", "conv", conv)
    if fun_mode.convertit_devise(n):
        return ("info", "devise", n)
    if RE_SYS_BATT.search(n):
        return ("sysinfo", "batterie", "")
    if RE_SYS_CPU.search(n):
        return ("sysinfo", "cpu", "")
    if RE_SYS_RAM.search(n):
        return ("sysinfo", "ram", "")
    if RE_SYS_UP.search(n):
        return ("sysinfo", "uptime", "")
    return None


def classify(text):
    """Retourne (mode, target, body) ou None si aucune règle ne matche."""
    n = core.normalize(text).strip(" .!?")
    if not n:
        return None
    cfg = core.CFG

    trig = core.normalize(cfg.get("modes", {}).get("emergency", {}).get("trigger", "urgence"))
    if trig and (n.count(trig) >= 2 or "mode urgence" in n or "sos sos" in n):
        return ("emergency", "", text)

    n = core.strip_politeness(n)

    # mise en veille : tout en haut, match plein ancré — la conversation
    # s'arrête sans bruit (« merci », « c'est tout », « stop »…)
    if RE_DISMISS.match(n.strip(" .!?,")):
        return ("dismiss", "", "")

    # choix vocal en attente (résultats YouTube) : « le deuxième » — TTL 90 s
    if PENDING_CHOICE["items"]:
        if time.time() - PENDING_CHOICE["t"] > 90:
            PENDING_CHOICE["items"] = []
        else:
            m = RE_CHOICE.match(n)
            if m:
                w = m.group(1)
                if w.startswith("numero "):
                    idx = int(w.split()[1]) - 1
                elif w.isdigit():
                    idx = int(w) - 1
                else:
                    idx = _ORDINAUX.get(w, 99)
                if idx == -1 or 0 <= idx < len(PENDING_CHOICE["items"]):
                    return ("yt_choice", str(idx), "")

    m = RE_PROFILE.match(n)
    if m and "profil" in n:
        return ("system", m.group(1).strip(), "")

    # raccourci vocal exact (« colle », « plein écran », « verrouille »…)
    sc = SHORTCUTS_VOICE.get(n)
    if sc:
        return ("shortcut", sc[0], sc[1])

    r = _classify_memory(n)
    if r is not None:
        return r

    if RE_BRIEFING.match(n):
        return ("briefing", "", "")

    # domotique : seulement si des entités Home Assistant sont configurées
    if cfg.get("ha_entities"):
        d = _classify_home(n)
        if d:
            return d

    # luminosité de l'ÉCRAN — après la domotique (une lumière HA nommée
    # garde la priorité), avant tout le reste
    m = RE_BRIGHT_SET.match(n)
    if m and 0 <= int(m.group(1)) <= 100:
        return ("bright", "set:" + m.group(1), "")
    m = RE_BRIGHT_REL.match(n)
    if m:
        sign = "-" if m.group(1).startswith(("baisse", "diminue", "reduis")) else "+"
        return ("bright", "rel:" + sign + "15", "")

    r = _classify_pc(n)
    if r is not None:
        return r

    # routines / mode boulot (« au boulot », « mode X »)
    routines = {core.normalize(k): k for k in (cfg.get("routines") or {})}
    rm = re.match(r"^(?:mode|lance (?:le |la )?mode|demarre (?:le |la )?mode)\s+(.+)$", n)
    key = None
    if rm and core.normalize(rm.group(1).strip()) in routines:
        key = routines[core.normalize(rm.group(1).strip())]
    elif n in ("au boulot", "on bosse", "je bosse", "mode travail", "mode bureau") \
            and "boulot" in routines:
        key = routines["boulot"]
    if key:
        return ("routine", key, "")

    # IPTV : « mets la télé », « zappe sur TF1 » (si une playlist est chargée)
    m = RE_IPTV.match(n)
    if m and (cfg.get("iptv") or {}).get("source"):
        chaine = (m.group(1) or m.group(2) or m.group(3) or "").strip(" .!?")
        return ("iptv", chaine, "")

    r = _classify_files(n)
    if r is not None:
        return r

    r = _classify_obsidian_notes(n)
    if r is not None:
        return r

    # capture d'écran complète horodatée (« capture complète » —
    # « capture d'écran » reste le raccourci Win+Shift+S de découpe)
    if RE_FULLSHOT.match(n):
        return ("screenshot", "", "")

    # agenda Google (lecture) — avant resolve_open (« mon agenda » ≠ le site)
    if RE_AGENDA.match(n):
        return ("agenda", "", "")

    # Google Docs / Sheets à la voix
    m = RE_GDOC_CREATE.match(n)
    if m:
        return ("gdoc", "create", (m.group(1) or "").strip(" .!?"))
    m = RE_GDOC_APPEND.match(n)
    if m:
        return ("gdoc", "append", m.group(1).strip())
    m = RE_GSHEET.match(n)
    if m:
        return ("gdoc", "sheet", (m.group(1) or "").strip(" .!?"))

    r = _classify_youtube_sport(n)
    if r is not None:
        return r

    # corbeille (phrase exacte — « ouvre la corbeille » reste une ouverture)
    if RE_TRASH.match(n):
        return ("trash", "", "")

    # recherche d'images — AVANT resolve_open (« montre-moi des photos de
    # chats » ne doit pas partir en ouverture d'appli)
    m = RE_IMAGES.match(n)
    if m:
        return ("images", m.group(1).strip(), "")

    # « lis mes mails » : lecture directe si Google est connecté (sinon Gmail web)
    if RE_MAILS.match(n):
        return ("mails", "", "")

    # sites et applis connus (« ouvre notion », « va sur youtube ») : instantané,
    # AVANT la navigation pour que « va sur youtube » n'ouvre pas Google Maps
    op = resolve_open(n)
    if op:
        return ("open", op[1], op[2])

    r = _classify_timers(n)
    if r is not None:
        return r

    r = _classify_infos(n)
    if r is not None:
        return r

    if RE_WEATHER.search(n):
        mc = RE_WEATHER_CITY.search(n)
        city = mc.group(1).strip() if mc else ""
        if city in ("demain", "aujourd'hui", "ce soir", "l'exterieur", "l'instant"):
            city = ""
        return ("weather", city, "")

    m = RE_CALENDAR.match(n)
    if m:
        return ("calendar", m.group(1).strip(), "")

    r = _classify_media_audio(n)
    if r is not None:
        return r

    # fermeture d'application (JARVIS) — APRÈS média (« stoppe la musique »)
    # et raccourcis (« ferme la fenêtre ») ; cible connue exigée, sinon IA
    m = RE_CLOSE_APP.match(n)
    if m:
        tgt = m.group(1).strip(" .!?")
        for art in ("l'application ", "l'appli ", "le logiciel ", "le ", "la ", "l'"):
            if tgt.startswith(art):
                tgt = tgt[len(art):].strip()
                break
        custom = {core.normalize(k).strip()
                  for k in (cfg.get("custom_apps") or {}) if k}
        if tgt and (tgt in APPS or tgt in custom or winext.find_window(tgt)):
            return ("close", tgt, "")

    r = _classify_messaging(n)
    if r is not None:
        return r

    # aide vocale : « que peux-tu faire ? »
    if n in _HELP_PHRASES:
        return ("help", "", "")

    # small-talk : matchs EXACTS uniquement, en tout dernier
    if n in _ST_HELLO:
        return ("smalltalk", "hello", "")
    if n in _ST_CAVA:
        return ("smalltalk", "cava", "")
    if n in _ST_WHO:
        return ("smalltalk", "who", "")
    if n in _ST_LOVE:
        return ("smalltalk", "love", "")

    return None


_MODE_LABELS = {
    "open": "l'ouverture intégrée", "shortcut": "un raccourci vocal intégré",
    "timer": "le minuteur intégré", "timer_cancel": "le minuteur intégré",
    "media": "une commande média intégrée", "volume": "le volume intégré",
    "window": "la gestion des fenêtres", "music": "la musique intégrée",
    "weather": "la météo intégrée", "time": "l'heure intégrée",
    "navigation": "la navigation intégrée", "message": "les messages intégrés",
    "call": "les appels intégrés", "calendar": "l'agenda intégré",
    "mails": "la lecture des mails",
}


def automation_conflict(auto):
    """Nom de la commande intégrée que cette automatisation masque, sinon ''.
    Une phrase qui déclenche déjà un mode interne rend l'automatisation
    redondante, voire nuisible (elle passe AVANT le mode)."""
    for p in auto.get("phrases", []):
        try:
            r = classify(p)
        except Exception:
            continue
        if r and r[0] in _MODE_LABELS:
            return _MODE_LABELS[r[0]]
    return ""


# ------------------------------------------------------------- handlers -----

def _enabled(mode):
    return core.CFG.get("modes", {}).get(mode, {}).get("enabled", True)


def handle(mode, target, body, raw_text):
    """Exécute un mode. Retourne {ok, reply, final, detail}."""
    if mode != "system" and not _enabled(mode):
        return {"ok": False, "reply": f"Le mode {mode} est désactivé dans les réglages",
                "final": raw_text, "detail": "mode désactivé"}
    return {
        "message": _do_message,
        "navigation": _do_navigation,
        "media": _do_media,
        "call": _do_call,
        "emergency": _do_emergency,
        "system": _do_system,
        "timer": _do_timer,
        "timer_cancel": _do_timer_cancel,
        "time": _do_time,
        "weather": _do_weather,
        "music": _do_music,
        "calendar": _do_calendar,
        "open": _do_open,
        "shortcut": _do_shortcut,
        "volume": _do_volume,
        "window": _do_window,
        "mails": _do_mails,
        "memory": _do_memory,
        "briefing": _do_briefing,
        "home": _do_home,
        "routine": _do_routine,
        "files": _do_files,
        "music_default": _do_music_default,
        "list": _do_list,
        "timer_at": _do_timer_at,
        "timer_adjust": _do_timer_adjust,
        "timer_count": _do_timer_count,
        "close": _do_close,
        "power": _do_power,
        "bright": _do_bright,
        "info": _do_info,
        "fun": _do_fun,
        "sysinfo": _do_sysinfo,
        "trash": _do_trash,
        "images": _do_images,
        "notes_voice": _do_notes_voice,
        "whereis": _do_whereis,
        "resto": _do_resto,
        "recall": _do_recall,
        "help": _do_help,
        "smalltalk": _do_smalltalk,
        "youtube": _do_youtube,
        "yt_choice": _do_yt_choice,
        "spotify_ctx": _do_spotify_ctx,
        "sport": _do_sport,
        "iptv": _do_iptv,
        "obsidian": _do_obsidian,
        "uninstall": _do_uninstall,
        "antivirus": _do_antivirus,
        "gdoc": _do_gdoc,
        "agenda": _do_agenda,
        "screenshot": _do_screenshot,
        "dismiss": lambda t, b, r: {"ok": True, "reply": "", "final": "", "detail": ""},
        # camera / visionwrite : interceptés par app.py (vision) — repli propre
        "camera": lambda t, b, r: {"ok": False, "reply": "La vision n'est pas "
                                   "disponible", "final": "", "detail": ""},
        "visionwrite": lambda t, b, r: {"ok": False, "reply": "La vision n'est "
                                        "pas disponible", "final": "", "detail": ""},
    }[mode](target, body, raw_text)


def _do_list(target, item, _raw):
    kind, _, lst = target.partition(":")
    label = "courses" if lst == "courses" else "tâches"
    if kind == "add":
        storage.list_add(item, lst)
        return {"ok": True, "reply": f"« {item} » ajouté à ta liste de {label}",
                "final": item, "detail": lst}
    if kind == "show":
        items = storage.list_items(lst)
        if not items:
            return {"ok": True, "reply": f"Ta liste de {label} est vide",
                    "final": "", "detail": lst}
        return {"ok": True,
                "reply": f"Liste de {label} ({len(items)}) : " + ", ".join(items),
                "final": ", ".join(items), "detail": lst}
    if kind == "clear":
        storage.list_clear(lst)
        return {"ok": True, "reply": f"Liste de {label} vidée", "final": "",
                "detail": lst}
    return {"ok": False, "reply": "Action liste inconnue", "final": "", "detail": ""}


def _do_music_default(service, _body, _raw):
    reply = _play_default_music(service)
    if not reply:
        # aucune playlist attitrée : on ouvre le service
        webbrowser.open(SITES["youtube"] if service == "youtube" else SITES["spotify"])
        return {"ok": True, "reply": "J'ouvre la musique (choisis ta playlist "
                "attitrée dans Réglages > Maison)", "final": service,
                "detail": "pas de playlist"}
    return {"ok": True, "reply": reply, "final": service, "detail": "musique attitrée"}


def _do_routine(key, _body, raw):
    routine = (core.CFG.get("routines") or {}).get(key) or []
    if not routine:
        return {"ok": False, "reply": f"La routine « {key} » est vide",
                "final": key, "detail": ""}
    launched = []
    for step in routine:
        t = (step or "").strip()
        try:
            if t.lower().startswith(("http://", "https://")):
                webbrowser.open(t)
            elif t.lower() == "musique" or t.lower() == "music":
                _play_default_music("")
            elif files_mode.resolve_folder(t):
                core.execute({"action": "open_app",
                              "target": files_mode.resolve_folder(t)})
            else:
                op = resolve_open("ouvre " + t)
                if op:
                    core.execute({"action": "open_url" if op[1].startswith("http")
                                  else "open_app", "target": op[1]})
                else:
                    core.execute({"action": "open_app", "target": t})
            launched.append(t)
            time.sleep(0.4)
        except Exception as e:
            core.log_err("routine " + t, e)
    # disposition en grille par TITRE de fenêtre, après 7 s (JARVIS) : les
    # applis lourdes ont le temps de s'ouvrir, les parasites sont ignorés
    threading.Timer(7.0, lambda: winext.grid_windows_by_titles(
        list(launched))).start()
    return {"ok": True, "reply": f"Espace « {key} » prêt : {len(launched)} éléments lancés",
            "final": ", ".join(launched), "detail": "routine"}


def _do_home(target, label, _raw):
    kind, _, eid = target.partition(":")
    if not integrations.ha_ready():
        return {"ok": False, "reply": "Home Assistant n'est pas connecté "
                "(Réglages > Maison)", "final": "", "detail": "non configuré"}
    try:
        if kind == "on":
            ok = integrations.ha_light(eid, "on")
            return {"ok": ok, "reply": f"J'allume {label}" if ok
                    else "La lumière n'a pas répondu", "final": label, "detail": eid}
        if kind == "off":
            ok = integrations.ha_light(eid, "off")
            return {"ok": ok, "reply": f"J'éteins {label}" if ok
                    else "La lumière n'a pas répondu", "final": label, "detail": eid}
        if kind == "color":
            ok = integrations.ha_light(eid, "on", rgb=COULEURS_RGB.get(label))
            return {"ok": ok, "reply": f"Lumière en {label}" if ok
                    else "Échec", "final": label, "detail": eid}
        if kind == "bright":
            ok = integrations.ha_light(eid, "on", brightness_pct=int(label))
            return {"ok": ok, "reply": f"Luminosité à {label} %" if ok
                    else "Échec", "final": label, "detail": eid}
        if kind in ("plugon", "plugoff"):
            ok = integrations.ha_call("switch",
                                      "turn_on" if kind == "plugon" else "turn_off", eid)
            return {"ok": ok, "reply": (f"Prise {label} allumée" if kind == "plugon"
                    else f"Prise {label} coupée") if ok else "Échec",
                    "final": label, "detail": eid}
        if kind == "temp":
            val = integrations.ha_state(eid)
            unit = integrations.ha_state(eid, "unit_of_measurement") or "°"
            if val is None:
                return {"ok": False, "reply": "Le capteur ne répond pas",
                        "final": label, "detail": eid}
            return {"ok": True, "reply": f"Il fait {val} {unit} dans {label}",
                    "final": f"{val} {unit}", "detail": eid}
        if kind == "read":
            val = integrations.ha_state(eid)
            unit = integrations.ha_state(eid, "unit_of_measurement") or ""
            if val is None:
                return {"ok": False, "reply": "Le capteur ne répond pas",
                        "final": label, "detail": eid}
            return {"ok": True, "reply": f"{label} : {val} {unit}".strip(),
                    "final": f"{val} {unit}", "detail": eid}
        if kind == "scene":
            ok = integrations.ha_scene(eid)
            return {"ok": ok, "reply": f"Scène {label} activée" if ok
                    else "La scène n'a pas répondu", "final": label, "detail": eid}
        if kind in ("all_on", "all_off"):
            ok = integrations.ha_all_lights(kind == "all_on")
            return {"ok": ok, "reply": ("Toutes les lumières allumées"
                    if kind == "all_on" else "Toutes les lumières éteintes")
                    if ok else "Échec", "final": kind, "detail": "light.all"}
        if kind == "toggle":
            if eid.startswith("switch."):
                ok = integrations.ha_call("switch", "toggle", eid)
            else:
                ok = integrations.ha_light(eid, "toggle")
            return {"ok": ok, "reply": f"Je bascule {label}" if ok else "Échec",
                    "final": label, "detail": eid}
        if kind == "clim":
            t = max(5, min(30, int(label)))
            ok = integrations.ha_climate_set(eid, t)
            return {"ok": ok, "reply": f"Chauffage réglé à {t} degrés" if ok
                    else "Le thermostat n'a pas répondu",
                    "final": f"{t} °C", "detail": eid}
        if kind in ("lock", "unlock"):
            ok = integrations.ha_lock(eid, kind == "lock")
            return {"ok": ok, "reply": (f"{label or 'La porte'} verrouillée"
                    if kind == "lock" else f"{label or 'La porte'} déverrouillée")
                    if ok else "Le verrou n'a pas répondu",
                    "final": label, "detail": eid}
        if kind in ("alarm_on", "alarm_off"):
            ok = integrations.ha_alarm(eid, kind == "alarm_on")
            return {"ok": ok, "reply": ("Alarme activée" if kind == "alarm_on"
                    else "Alarme désactivée") if ok else "L'alarme n'a pas répondu",
                    "final": kind, "detail": eid}
        if kind == "vac":
            act, _, eid2 = eid.partition(":")
            ok = integrations.ha_vacuum(eid2, act)
            labels = {"start": "Aspirateur lancé", "stop": "Aspirateur arrêté",
                      "pause": "Aspirateur en pause",
                      "dock": "L'aspirateur rentre à sa base"}
            return {"ok": ok, "reply": labels.get(act, "Fait") if ok
                    else "L'aspirateur n'a pas répondu", "final": act, "detail": eid2}
    except Exception as e:
        return {"ok": False, "reply": "Home Assistant injoignable",
                "final": "", "detail": str(e)[:80]}
    return {"ok": False, "reply": "Commande maison inconnue", "final": "", "detail": ""}


def _resolve_files_arg(arg):
    if arg == "@last":
        return LAST_FOLDER["path"] or None
    return files_mode.resolve_folder(arg)


def _do_files(target, body, _raw):
    kind, _, arg = target.partition(":")
    if kind in ("sort", "sortdate", "sortdatetype"):
        path = _resolve_files_arg(arg)
        if not path:
            return {"ok": False, "reply": "Quel dossier ?", "final": arg,
                    "detail": "dossier inconnu"}
        LAST_FOLDER["path"] = path
        if kind == "sort":
            ok, msg = files_mode.sort_folder(path)
        else:
            ok, msg = files_mode.sort_folder_by_date(
                path, with_type=(kind == "sortdatetype"))
        return {"ok": ok, "reply": msg, "final": arg, "detail": path}
    if kind == "find":
        found = files_mode.find_file(arg)
        if not found:
            return {"ok": False, "reply": f"Aucun fichier « {arg} » trouvé",
                    "final": arg, "detail": "recherche"}
        subprocess.Popen(f'explorer /select,"{found}"', shell=True)
        return {"ok": True, "reply": f"Trouvé : {os.path.basename(found)}",
                "final": found, "detail": "sélectionné"}
    if kind == "mkdir":
        created = files_mode.make_folder(arg, base=body or "documents")
        if not created:
            return {"ok": False, "reply": "Je n'ai pas pu créer le dossier",
                    "final": arg, "detail": ""}
        LAST_FOLDER["path"] = created
        core.execute({"action": "open_app", "target": created})
        return {"ok": True,
                "reply": f"Dossier « {os.path.basename(created)} » créé",
                "final": created, "detail": created}
    if kind == "ls":
        path = _resolve_files_arg(arg)
        res = files_mode.folder_summary(path)
        if not res:
            return {"ok": False, "reply": "Dossier introuvable", "final": arg,
                    "detail": ""}
        LAST_FOLDER["path"] = path
        cats = ", ".join(f"{v} {k.lower()}" for k, v in
                         sorted(res["counts"].items(), key=lambda x: -x[1])[:4])
        reply = f"{res['total']} fichiers"
        if cats:
            reply += f" ({cats})"
        if res["dirs"]:
            reply += f" et {res['dirs']} dossiers"
        return {"ok": True, "reply": reply, "final": arg, "detail": path}
    if kind == "quad" or target == "quad":
        opened = []
        for d in ("documents", "telechargements", "images", "videos"):
            p = files_mode.resolve_folder(d)
            if p:
                core.execute({"action": "open_app", "target": p})
                opened.append(d)
                time.sleep(0.8)
        threading.Timer(1.5, lambda: winext.grid_windows(len(opened))).start()
        return {"ok": True, "reply": f"{len(opened)} dossiers ouverts en mosaïque",
                "final": ", ".join(opened), "detail": "quad"}
    return {"ok": False, "reply": "Action fichier inconnue", "final": "", "detail": ""}


def _play_default_music(service_hint):
    """« Mets de la musique » → playlist Spotify attitrée (ou YouTube)."""
    music = core.CFG.get("music") or {}
    if "youtube" in service_hint and music.get("youtube_url"):
        webbrowser.open(music["youtube_url"])
        return "Musique lancée sur YouTube"
    uri = music.get("spotify_uri", "")
    if uri and integrations.spotify_connected():
        try:
            if integrations.spotify_play_context(uri):
                return "Je lance ta playlist"
        except Exception as e:
            core.log_err("music ctx", e)
    if uri:
        # URI spotify:playlist:xxxx → lien web ouvrable
        pid = uri.split(":")[-1]
        webbrowser.open(f"https://open.spotify.com/playlist/{pid}")
        return "J'ouvre ta playlist Spotify"
    if music.get("youtube_url"):
        webbrowser.open(music["youtube_url"])
        return "Musique lancée sur YouTube"
    return ""


def _do_open(target, name, raw):
    if target.startswith("http"):
        core.execute({"action": "open_url", "target": target})
        return {"ok": True, "reply": f"J'ouvre {name}", "final": raw, "detail": target}
    # cascade JARVIS : App Paths du registre → PATH → dossiers usuels.
    # Un nom simple introuvable = échec HONNÊTE (l'IA prend le relais),
    # au lieu d'un « start » silencieux qui ne fait rien.
    t = target
    plain = (not t.lower().startswith(("ms-", "shell:", "spotify:", "deezer:",
                                       "steam:", "com.", "minecraft"))
             and "\\" not in t and "/" not in t and " " not in t
             and not t.lower().endswith((".exe", ".bat", ".lnk")))
    if plain:
        exe = winext.resolve_exe(t)
        if exe:
            t = exe
        else:
            import shutil as _sh
            if not _sh.which(t):
                return {"ok": False,
                        "reply": f"Je ne trouve pas {name} sur ce PC",
                        "final": raw, "detail": f"{target} introuvable"}
    if os.path.isdir(t):
        LAST_FOLDER["path"] = t      # « trie ce dossier » sait de qui on parle
    core.execute({"action": "open_app", "target": t})
    return {"ok": True, "reply": f"J'ouvre {name}", "final": raw, "detail": t}


def _do_shortcut(target, label, raw):
    core.execute({"action": "keys", "target": target})
    return {"ok": True, "reply": label or "Fait", "final": raw, "detail": target}


def _do_volume(kind, value, _raw):
    if kind == "set":
        pct = max(0, min(100, int(value)))
        ok = winext.set_volume(pct)
        return {"ok": ok, "reply": f"Volume à {pct} %" if ok
                else "Je n'arrive pas à régler le volume",
                "final": f"{pct} %", "detail": "volume maître"}
    if kind == "rel":
        new = winext.change_volume(int(value))
        return {"ok": new is not None,
                "reply": f"Volume à {new} %" if new is not None
                else "Je n'arrive pas à régler le volume",
                "final": f"{value} pts", "detail": "volume relatif"}
    if kind == "app":
        delta, _, app = value.partition("|")
        noms, pct = winext.set_app_volume(app, delta=int(delta))
        if not noms:
            return {"ok": False, "reply": f"Aucune appli « {app} » ne joue de son",
                    "final": app, "detail": "session audio introuvable"}
        return {"ok": True,
                "reply": f"Volume de {', '.join(sorted(set(noms)))} à {pct} %",
                "final": app, "detail": f"{delta} pts"}
    # mute_app / unmute_app
    mute = kind == "mute_app"
    apps = winext.set_app_mute(value, mute)
    if not apps:
        return {"ok": False, "reply": f"Aucune appli « {value} » ne joue de son",
                "final": value, "detail": "session audio introuvable"}
    name = ", ".join(sorted(set(apps)))
    return {"ok": True, "reply": ("Son coupé : " if mute else "Son rétabli : ") + name,
            "final": name, "detail": f"mute={mute}"}


def _do_window(action, target, raw):
    if action == "split":
        a, _, b = target.partition("||")
        res = winext.side_by_side(a, b)
        if not res:
            return {"ok": False,
                    "reply": f"Je ne trouve pas les fenêtres « {a} » et « {b} »",
                    "final": target, "detail": "fenêtres introuvables"}
        return {"ok": True, "reply": f"Côte à côte : {a} et {b}",
                "final": f"{res[0]} | {res[1]}", "detail": "split"}
    title = winext.focus_window(target)
    if title:
        return {"ok": True, "reply": f"Je bascule sur {target}",
                "final": title, "detail": "focus"}
    # pas de fenêtre ouverte : on ouvre le site/l'appli si on le connaît
    op = resolve_open("ouvre " + target)
    if op:
        return _do_open(op[1], op[2], raw)
    return {"ok": False, "reply": f"Aucune fenêtre « {target} » ouverte",
            "final": target, "detail": "introuvable"}


def _do_memory(kind, content, _raw):
    if kind == "dismiss":
        return {"ok": True, "reply": "OK, on oublie", "final": "",
                "detail": "rétractation"}
    if kind == "remember":
        storage.add_fact(content)
        return {"ok": True, "reply": "C'est retenu", "final": content,
                "detail": "mémoire durable"}
    gone = storage.forget_fact(content)
    if gone:
        return {"ok": True, "reply": f"Oublié : {gone[:60]}", "final": gone,
                "detail": "mémoire durable"}
    return {"ok": False, "reply": "Je ne trouve pas ça dans ma mémoire",
            "final": content, "detail": "aucun fait proche"}


def _do_briefing(_target, _body, _raw):
    now = datetime.now()
    parts = [f"Il est {now.hour} h {now.minute:02d}, "
             f"{_JOURS[now.weekday()]} {now.day} {_MOIS[now.month - 1]}"]
    if integrations.is_online():
        try:
            w = integrations.weather("")
            parts.append(f"{w['desc']}, {w['temp']} degrés")
        except Exception:
            pass
    act = timers.list_active()
    if act:
        t = act[0]
        parts.append(f"{len(act)} minuteur{'s' if len(act) > 1 else ''} en cours "
                     f"({timers.human(t['remaining'])} restantes)")
    if integrations.google_connected():
        try:
            mails = integrations.gmail_unread(3)
            if mails:
                parts.append(f"{len(mails)} mails non lus, dont "
                             f"{mails[0]['from']} — {mails[0]['subject'][:40]}")
            else:
                parts.append("aucun mail non lu")
        except Exception:
            pass
        try:
            evs = integrations.gcal_events(1)
            if evs:
                parts.append(f"prochain rendez-vous : {evs[0]['titre']}")
        except Exception:
            pass
    if integrations.is_online():
        try:
            al = integrations.weather_alerts()
            if al:
                parts.append("attention : " + ", ".join(al[:2]))
        except Exception:
            pass
    reply = ". ".join(parts)
    return {"ok": True, "reply": reply, "final": reply, "detail": "briefing"}


def _do_mails(_target, _body, raw):
    if not integrations.google_connected():
        # pas de compte relié : on ouvre Gmail web, comme avant
        webbrowser.open(SITES["gmail"])
        return {"ok": True, "reply": "J'ouvre Gmail (connecte ton compte dans "
                "Réglages > Comptes pour que je te les lise)",
                "final": "gmail web", "detail": "non connecté"}
    try:
        mails = integrations.gmail_unread(3)
    except Exception as e:
        return {"ok": False, "reply": "Gmail ne répond pas, réessaie",
                "final": "", "detail": str(e)[:120]}
    if not mails:
        return {"ok": True, "reply": "Aucun nouveau mail", "final": "0 mail",
                "detail": "inbox à jour"}
    lines = " · ".join(f"{m['from']} — {m['subject']}" for m in mails)
    n = len(mails)
    return {"ok": True,
            "reply": (f"{n} nouveau mail : " if n == 1 else f"{n} nouveaux mails : ") + lines,
            "final": lines, "detail": "gmail api"}


def _do_navigation(target, _body, _raw):
    dest = target.strip()
    if not dest:
        return {"ok": False, "reply": "Je n'ai pas compris la destination", "final": "", "detail": ""}
    app = core.CFG.get("modes", {}).get("navigation", {}).get("app", "gmaps")
    if app == "waze":
        url = f"https://waze.com/ul?q={urllib.parse.quote(dest)}&navigate=yes"
    else:
        url = (f"https://www.google.com/maps/dir/?api=1&destination="
               f"{urllib.parse.quote(dest)}&travelmode=driving")
    webbrowser.open(url)
    return {"ok": True, "reply": f"Navigation vers {dest}", "final": dest, "detail": url}


def _do_media(target, _body, _raw):
    ok = winext.send_media_key(target)
    label = winext.MEDIA_LABELS.get(target, target)
    return {"ok": ok, "reply": f"OK, {label}" if ok else "La commande média a échoué",
            "final": label, "detail": f"media {target}"}


def _call_whatsapp(contact_name):
    """Appel WhatsApp Desktop au clavier (séquence et timings JARVIS) :
    ouvrir → chercher le contact → Entrée → Ctrl+Maj+C (appel audio)."""
    import keyboard

    def go():
        try:
            try:
                os.startfile("whatsapp:")
            except OSError:
                webbrowser.open("https://web.whatsapp.com")
            time.sleep(6.0)
            keyboard.send("ctrl+f")
            time.sleep(1.0)
            winext.set_clipboard(contact_name)
            keyboard.send("ctrl+v")
            time.sleep(2.0)
            keyboard.send("enter")
            time.sleep(3.0)
            keyboard.send("ctrl+shift+c")
        except Exception as e:
            core.log_err("call_whatsapp", e)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True,
            "reply": f"J'appelle {contact_name} sur WhatsApp — vérifie l'écran",
            "final": contact_name, "detail": "whatsapp ctrl+shift+c"}


def _do_call(target, _body, _raw):
    # « appelle paul sur whatsapp » : pilotage de l'appli (JARVIS)
    nraw = core.normalize(_raw or "")
    if "whatsapp" in nraw:
        clean = re.sub(r"\s+(?:sur|via|avec)\s+whatsapp$", "",
                       target.strip())
        return _call_whatsapp(clean or target)
    contact = find_contact(target)
    if not contact or not contact.get("phone"):
        return {"ok": False, "reply": f"Je ne trouve pas {target or 'ce contact'} dans les contacts",
                "final": target, "detail": "contact introuvable"}
    if integrations.twilio_ready(core.CFG):
        try:
            integrations.place_call(core.CFG, contact["phone"])
            return {"ok": True, "reply": f"J'appelle {contact['name']} via Twilio",
                    "final": contact["name"], "detail": f"twilio → {contact['phone']}"}
        except Exception as e:
            detail = f"twilio erreur : {e}"
    else:
        detail = "twilio non configuré"
    tel = re.sub(r"[^+0-9]", "", contact["phone"])
    webbrowser.open(f"tel:{tel}")
    return {"ok": True, "reply": f"J'ouvre l'appel vers {contact['name']}",
            "final": contact["name"], "detail": f"tel: ({detail})"}


def _wa_open(phone, text):
    num = re.sub(r"[^0-9]", "", phone)
    webbrowser.open(f"https://wa.me/{num}?text={urllib.parse.quote(text)}")


def _gmail_compose(to, subject, body):
    webbrowser.open("https://mail.google.com/mail/?view=cm&fs=1&to="
                    + urllib.parse.quote(to) + "&su=" + urllib.parse.quote(subject)
                    + "&body=" + urllib.parse.quote(body))


def _do_message(target, body, raw):
    cfg = core.CFG
    text = core.format_message(body)
    text = core.translate_if_needed(text)
    contact = find_contact(target)
    delivery = cfg.get("modes", {}).get("message", {}).get("delivery", "auto")

    # canal demandé à la voix : « envoie un whatsapp / un mail / un sms à… »
    nraw = core.normalize(raw)
    channel = ""
    if "whatsapp" in nraw:
        channel = "whatsapp"
    elif re.search(r"\b(mail|email|courriel)\b", nraw):
        channel = "email"
    elif re.search(r"\b(sms|texto)\b", nraw):
        channel = "sms"

    if channel == "whatsapp" or (not channel and delivery == "whatsapp"):
        if contact and contact.get("phone"):
            _wa_open(contact["phone"], text)
            return {"ok": True,
                    "reply": f"WhatsApp ouvert pour {contact['name']} — Entrée pour envoyer",
                    "final": text, "detail": f"whatsapp → {contact['phone']}"}
        if channel == "whatsapp":
            return {"ok": False,
                    "reply": f"Pas de numéro pour {target or 'ce contact'} (Réglages > Profils)",
                    "final": text, "detail": "whatsapp : contact sans numéro"}

    if channel == "email":
        if not contact or not contact.get("email"):
            return {"ok": False,
                    "reply": f"Pas d'adresse mail pour {target or 'ce contact'} (Réglages > Profils)",
                    "final": text, "detail": "email : contact sans adresse"}
        if integrations.graph_connected():
            try:
                if integrations.graph_send_mail(contact["email"], "Message de Nova", text):
                    return {"ok": True, "reply": f"Mail envoyé à {contact['name']}",
                            "final": text, "detail": f"mail → {contact['email']}"}
            except Exception:
                pass
        _gmail_compose(contact["email"], "", text)
        return {"ok": True, "reply": f"Brouillon Gmail ouvert pour {contact['name']}",
                "final": text, "detail": f"gmail → {contact['email']}"}

    if contact and contact.get("phone") and delivery in ("auto", "twilio") \
            and integrations.twilio_ready(cfg):
        try:
            integrations.send_sms(cfg, contact["phone"], text)
            return {"ok": True, "reply": f"Message envoyé à {contact['name']}",
                    "final": text, "detail": f"SMS twilio → {contact['phone']}"}
        except Exception as e:
            if delivery == "twilio":
                return {"ok": False, "reply": "L'envoi du SMS a échoué",
                        "final": text, "detail": f"twilio : {e}"}
    if channel == "sms" and contact and contact.get("phone") \
            and not integrations.twilio_ready(cfg):
        _wa_open(contact["phone"], text)
        return {"ok": True,
                "reply": f"Twilio non configuré — WhatsApp ouvert pour {contact['name']}",
                "final": text, "detail": "sms → fallback whatsapp"}
    if contact and contact.get("email") and delivery == "auto" and integrations.graph_connected():
        try:
            if integrations.graph_send_mail(contact["email"], "Message de Nova", text):
                return {"ok": True, "reply": f"Mail envoyé à {contact['name']}",
                        "final": text, "detail": f"mail → {contact['email']}"}
        except Exception:
            pass
    pasted = winext.paste_into_active_app(text)
    extra = "" if contact or not target else f" (contact {target} inconnu)"
    return {"ok": True,
            "reply": ("Message collé dans l'application active" if pasted
                      else "Message copié dans le presse-papiers") + extra,
            "final": text, "detail": "clipboard"}


# ------------------------------------- nouveaux handlers (héritage JARVIS) --

def home_step(action, name):
    """Étape domotique déléguée par l'IA (action LLM « home »)."""
    try:
        eid, _n = _ha_entity(name, ("light", "switch"))
        if not eid:
            return False
        a = core.normalize(action or "").strip()
        if a in ("on", "off", "toggle"):
            if eid.startswith("switch."):
                svc = {"on": "turn_on", "off": "turn_off"}.get(a, "toggle")
                return integrations.ha_call("switch", svc, eid)
            return integrations.ha_light(eid, a)
        if a.startswith("color"):
            c = a.split(None, 1)[1].strip() if " " in a else ""
            rgb = COULEURS_RGB.get(c)
            return integrations.ha_light(eid, "on", rgb=rgb) if rgb else False
        if a.startswith("bright"):
            mm = re.search(r"\d+", a)
            if not mm:
                return False
            return integrations.ha_light(eid, "on", brightness_pct=int(mm.group(0)))
    except Exception as e:
        core.log_err("home_step", e)
    return False


def _do_recall(fact, _body, _raw):
    return {"ok": True, "reply": "D'après ma mémoire : " + fact,
            "final": fact, "detail": "mémoire locale"}


def _do_timer_at(target, texte, _raw):
    hhmm, _, flag = target.partition("|")
    daily = flag == "d"
    storage.reminder_add(texte, hhmm, daily)
    h, mn = hhmm.split(":")
    when = f"{int(h)} h {mn}"
    return {"ok": True,
            "reply": f"Je te rappellerai « {texte} » à {when}"
                     + (" tous les jours" if daily else ""),
            "final": texte, "detail": hhmm + (" quotidien" if daily else "")}


def _do_timer_adjust(target, _body, _raw):
    delta = int(target)
    res = timers.adjust(delta)
    if not res:
        return {"ok": False, "reply": "Aucun minuteur en cours",
                "final": "", "detail": ""}
    label, remaining = res
    lbl = f" « {label} »" if label else ""
    verb = "prolongé" if delta > 0 else "raccourci"
    return {"ok": True,
            "reply": f"Minuteur{lbl} {verb} : il reste {timers.human(remaining)}",
            "final": timers.human(remaining), "detail": f"{delta:+d} s"}


def _do_timer_count(_target, _body, _raw):
    act = timers.list_active()
    try:
        rem = [r for r in storage.reminders_list() if not r["triggered"]]
    except Exception:
        rem = []
    if not act and not rem:
        return {"ok": True, "reply": "Aucun minuteur ni rappel en cours",
                "final": "0", "detail": ""}
    parts = []
    if act:
        t = act[0]
        parts.append(f"{len(act)} minuteur{'s' if len(act) > 1 else ''} en cours, "
                     f"le prochain se termine dans {timers.human(t['remaining'])}")
    if rem:
        parts.append(f"{len(rem)} rappel{'s programmés' if len(rem) > 1 else ' programmé'}")
    return {"ok": True, "reply": " ; ".join(parts),
            "final": f"{len(act)}+{len(rem)}", "detail": "compteur"}


def _do_close(target, _body, _raw):
    nb = winext.close_app(target)
    if not nb and target in APPS and not APPS[target].startswith(("ms-", "shell:")):
        nb = winext.close_app(APPS[target])
    if nb:
        return {"ok": True, "reply": f"J'ai fermé {target}",
                "final": target, "detail": f"{nb} fermé(s)"}
    return {"ok": False, "reply": f"{target.capitalize()} ne semble pas lancé",
            "final": target, "detail": "introuvable"}


_PENDING_SHUTDOWN = {"t": 0.0}


def _do_power(kind, body, _raw):
    flags = {"shell": True, "creationflags": 0x08000000}   # CREATE_NO_WINDOW
    if kind == "sleep":
        subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", **flags)
        return {"ok": True, "reply": "Mise en veille…", "final": "veille",
                "detail": "SetSuspendState"}
    if kind == "cancel":
        r = subprocess.run("shutdown /a", capture_output=True, **flags)
        ok = r.returncode == 0
        return {"ok": True,
                "reply": "Arrêt annulé" if ok else "Aucun arrêt n'était programmé",
                "final": "", "detail": "shutdown /a"}
    if kind == "reboot":
        subprocess.Popen("shutdown /r /t 30", **flags)
        return {"ok": True, "reply": "Redémarrage dans 30 secondes — dis "
                "« annule l'arrêt » pour annuler", "final": "reboot",
                "detail": "shutdown /r /t 30"}
    if kind.startswith("off:"):
        secs = max(10, int(kind[4:]))
        subprocess.Popen(f"shutdown /s /t {secs}", **flags)
        return {"ok": True, "reply": f"Arrêt du PC dans {timers.human(secs)} — "
                "« annule l'arrêt » pour annuler", "final": timers.human(secs),
                "detail": f"shutdown /s /t {secs}"}
    if kind == "off_ask":
        _PENDING_SHUTDOWN["t"] = time.time()
        return {"ok": True, "reply": "Pour confirmer, dis : "
                "« confirme l'arrêt du PC »", "final": "",
                "detail": "confirmation demandée"}
    if kind == "off_do":
        if time.time() - _PENDING_SHUTDOWN["t"] > 60:
            return {"ok": False, "reply": "La demande d'arrêt a expiré — "
                    "redemande d'abord d'éteindre le PC", "final": "",
                    "detail": "expirée"}
        _PENDING_SHUTDOWN["t"] = 0.0
        subprocess.Popen("shutdown /s /t 10", **flags)
        return {"ok": True, "reply": "Arrêt dans 10 secondes — "
                "« annule l'arrêt » pour annuler", "final": "arrêt",
                "detail": "shutdown /s /t 10"}
    return {"ok": False, "reply": "Commande d'alimentation inconnue",
            "final": "", "detail": kind}


def _do_bright(target, _body, _raw):
    kind, _, val = target.partition(":")
    if kind == "set":
        ok = winext.set_brightness(int(val))
        return {"ok": ok, "reply": f"Luminosité à {val} %" if ok
                else "Cet écran ne permet pas le réglage de luminosité "
                     "(moniteur externe ?)", "final": val + " %",
                "detail": "WMI"}
    new = winext.change_brightness(int(val))
    return {"ok": new is not None,
            "reply": f"Luminosité à {new} %" if new is not None
            else "Cet écran ne permet pas le réglage de luminosité",
            "final": f"{val} pts", "detail": "WMI relatif"}


def _taux_eur_usd():
    if not integrations.is_online():
        return None
    import requests
    r = requests.get("https://api.frankfurter.app/latest?from=EUR&to=USD",
                     timeout=4)
    return float(r.json()["rates"]["USD"])


def _do_info(kind, arg, _raw):
    reply = None
    detail = kind
    if kind == "city_time":
        reply = fun_mode.heure_ville(arg)
    elif kind == "capitale":
        cap = fun_mode.capitale(arg)
        reply = f"La capitale, c'est {cap}" if cap else None
    elif kind == "monnaie":
        mo = fun_mode.monnaie(arg)
        reply = f"C'est {mo}" if mo else None
    elif kind == "spell":
        ep = fun_mode.epelle(arg)
        reply = f"{arg} s'épelle : {ep}" if ep else None
    elif kind == "otan":
        reply = fun_mode.otan(arg)
    elif kind == "coin":
        reply = fun_mode.pile_ou_face()
    elif kind == "dice":
        reply = fun_mode.de(int(arg or 6))
    elif kind == "rand":
        a, _, b = arg.partition("|")
        reply = "Je dis " + fun_mode.nombre(a or 1, b or 100)
    elif kind == "password":
        pw = fun_mode.mot_de_passe(int(arg or 16))
        winext.set_clipboard(pw)
        # JAMAIS prononcé, jamais dans l'historique (final vide)
        return {"ok": True, "reply": f"Mot de passe de {len(pw)} caractères "
                "copié dans le presse-papiers", "final": "",
                "detail": "jamais affiché ni enregistré"}
    elif kind == "countdown":
        reply = fun_mode.compte_a_rebours(arg)
    elif kind == "calc":
        reply = arg          # déjà calculé par classify
    elif kind == "conv":
        reply = arg
    elif kind == "devise":
        reply = fun_mode.convertit_devise(arg, taux_live=_taux_eur_usd)
        detail = "frankfurter/indicatif"
    if not reply:
        return {"ok": False, "reply": "Je n'ai pas trouvé", "final": "",
                "detail": detail}
    return {"ok": True, "reply": reply, "final": reply, "detail": detail}


def _do_fun(kind, _body, _raw):
    reply = fun_mode.blague() if kind == "blague" else fun_mode.citation()
    return {"ok": True, "reply": reply, "final": reply, "detail": kind}


def _do_sysinfo(kind, _body, _raw):
    try:
        reply = fun_mode.sysinfo(kind)
    except Exception as e:
        return {"ok": False, "reply": "Je n'arrive pas à lire cette information",
                "final": "", "detail": str(e)[:80]}
    return {"ok": bool(reply), "reply": reply or "Information indisponible",
            "final": reply or "", "detail": "psutil"}


def _do_trash(_target, _body, _raw):
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=30, creationflags=0x08000000)
        return {"ok": True, "reply": "Corbeille vidée", "final": "",
                "detail": "Clear-RecycleBin"}
    except Exception as e:
        return {"ok": False, "reply": "Je n'ai pas pu vider la corbeille",
                "final": "", "detail": str(e)[:80]}


def _do_images(query, _body, _raw):
    # version riche (JARVIS/SerpAPI/DuckDuckGo) : grille locale design Nova ;
    # repli honnête sur Google Images si aucune image ne revient
    urls = []
    if integrations.is_online():
        try:
            import webinfo
            urls = webinfo.chercher_images(query, 6)
        except Exception as e:
            core.log_err("images", e)
    if urls:
        import html as _html
        import tempfile
        q = _html.escape(query)
        cells = "".join(
            f'<a href="{_html.escape(u, quote=True)}" target="_blank">'
            f'<img src="{_html.escape(u, quote=True)}" loading="lazy" '
            "style='width:100%;height:220px;object-fit:cover;border-radius:12px;"
            "border:1px solid rgba(255,255,255,.08)'></a>" for u in urls)
        page = ("<!doctype html><meta charset='utf-8'>"
                f"<title>Nova — images de {q}</title>"
                "<body style='margin:0;background:#141826;"
                "font-family:Segoe UI,sans-serif'>"
                f"<h2 style='color:#f2f5ff;padding:18px 22px;margin:0;"
                f"font-size:17px'>Images de {q}</h2>"
                "<div style='display:grid;grid-template-columns:repeat(3,1fr);"
                f"gap:10px;padding:0 22px 22px'>{cells}</div></body>")
        p = os.path.join(tempfile.gettempdir(), "nova_images.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(page)
        webbrowser.open(p)
        return {"ok": True, "reply": f"Voici {len(urls)} images de {query}",
                "final": query, "detail": "grille locale"}
    webbrowser.open("https://www.google.com/search?tbm=isch&q="
                    + urllib.parse.quote(query))
    return {"ok": True, "reply": f"Voici des images de {query}",
            "final": query, "detail": "google images"}


def _do_notes_voice(kind, _body, _raw):
    notes = core.get_notes()
    if kind == "show":
        if not notes:
            return {"ok": True, "reply": "Tu n'as aucune note", "final": "0",
                    "detail": "notes"}
        derniers = notes[:5]
        titres = " ; ".join(nt.get("title", "Sans titre") for nt in derniers)
        return {"ok": True,
                "reply": f"Tes {len(derniers)} dernières notes : {titres}",
                "final": titres, "detail": f"{len(notes)} au total"}
    # clear — phrase complète exigée par la regex
    count = len(notes)
    if not count:
        return {"ok": True, "reply": "Il n'y avait aucune note", "final": "0",
                "detail": "notes"}
    for nt in list(notes):
        core.delete_note(nt["id"])
    return {"ok": True, "reply": f"{count} note{'s' if count > 1 else ''} "
            f"supprimée{'s' if count > 1 else ''}", "final": str(count),
            "detail": "tout effacé"}


def _do_whereis(place, _body, _raw):
    webbrowser.open("https://www.google.com/maps/search/"
                    + urllib.parse.quote(place))
    return {"ok": True, "reply": f"Je te montre où se trouve {place}",
            "final": place, "detail": "maps"}


_LAST_RESTOS = {"items": [], "offset": 0}


def _do_resto(place, _body, _raw):
    # « d'autres restaurants » : la suite de la dernière liste
    if place == "@more":
        items = _LAST_RESTOS["items"]
        off = _LAST_RESTOS["offset"]
        if not items or off >= len(items):
            return {"ok": False, "reply": "Je n'ai plus d'autres restaurants "
                    "sous la main", "final": "", "detail": ""}
        suite = items[off:off + 3]
        _LAST_RESTOS["offset"] = off + 3
        lignes = " ; ".join(f"{r['nom']} ({r['note']}/5)" for r in suite)
        return {"ok": True, "reply": "Il y a aussi : " + lignes,
                "final": str(len(suite)), "detail": "suite"}
    # version riche SerpAPI (JARVIS) si clé présente, sinon Google Maps
    if integrations.is_online() and winext.has_secret("serpapi"):
        try:
            import webinfo
            res = webinfo.restaurants(place)
        except Exception as e:
            core.log_err("restaurants", e)
            res = []
        if res:
            _LAST_RESTOS.update(items=res, offset=3)
            lignes = " ; ".join(f"{r['nom']} ({r['note']}/5)" for r in res[:3])
            ou = f"à {place}" if place else "près de toi"
            return {"ok": True,
                    "reply": f"Les mieux notés {ou} : {lignes}. "
                             "Dis « d'autres restaurants » pour la suite",
                    "final": str(len(res)), "detail": "serpapi"}
    q = "restaurants" + (f" {place}" if place else "")
    webbrowser.open("https://www.google.com/maps/search/" + urllib.parse.quote(q))
    return {"ok": True,
            "reply": f"Voici les restaurants {('à ' + place) if place else 'autour de toi'}",
            "final": q, "detail": "maps"}


def _do_help(_target, _body, _raw):
    reply = random.choice([
        "Je t'ouvre la page « Que dire ? » : tout ce que je comprends y est",
        "Regarde, voilà tout ce que je sais faire",
        "La liste complète de mes commandes s'affiche",
    ])
    return {"ok": True, "reply": reply, "final": "", "detail": "aide"}


def _do_smalltalk(kind, _body, _raw):
    h = datetime.now().hour
    if kind == "hello":
        salut = "Bonsoir" if h >= 18 else ("Bon après-midi" if h >= 12 else "Salut")
        reply = random.choice([
            f"{salut} ! Qu'est-ce que je peux faire pour toi ?",
            f"{salut} ! Je t'écoute",
            f"{salut} ! Dis-moi tout",
        ])
    elif kind == "cava":
        reply = random.choice([
            "Très bien, tous mes circuits répondent ! Et toi ?",
            "En pleine forme, prête à t'aider",
            "Ça va très bien — dis-moi ce qu'il te faut",
        ])
    elif kind == "who":
        reply = random.choice([
            "Je suis Nova, ton assistante vocale : minuteurs, musique, maison "
            "connectée, fichiers, questions… demande-moi ce que tu veux",
            "Nova, ton assistante sur ce PC. Dis « que peux-tu faire » pour "
            "voir tout ce que je sais faire",
        ])
    else:   # love
        reply = random.choice([
            "Merci ! Je fais de mon mieux",
            "C'est gentil, merci !",
            "Merci — toujours là pour toi",
        ])
    return {"ok": True, "reply": reply, "final": reply, "detail": "small-talk"}


# ---------------------------------------- handlers Vague 3 (JARVIS 2.14) ----

LAST_FOLDER = {"path": ""}
av_notify = None   # callback(msg) branché par app.py (fin de scan antivirus)


def _do_youtube(kind, arg, _raw):
    import yt_mode
    if not yt_mode.ready():
        if kind == "search":
            webbrowser.open("https://www.youtube.com/results?search_query="
                            + urllib.parse.quote(arg))
            return {"ok": True, "reply": f"Je cherche « {arg} » sur YouTube",
                    "final": arg, "detail": "sans clé API"}
        return {"ok": False, "reply": "Ajoute une clé API YouTube "
                "(Réglages > Système) pour cette commande", "final": "",
                "detail": "clé absente"}
    try:
        if kind == "search":
            res = yt_mode.chercher_multi(arg, 5)
            if not res:
                return {"ok": False, "reply": f"Rien trouvé pour « {arg} »",
                        "final": arg, "detail": "youtube api"}
            PENDING_CHOICE.update(items=[r["url"] for r in res], t=time.time())
            lignes = " ; ".join(f"{i + 1}. {r['titre']} ({r['chaine']})"
                                for i, r in enumerate(res[:5]))
            return {"ok": True,
                    "reply": f"J'ai trouvé : {lignes}. Dis « le premier », "
                             "« le deuxième »…",
                    "final": arg, "detail": f"{len(res)} résultats"}
        if kind == "resume":
            url = arg or (PENDING_CHOICE["items"][0]
                          if PENDING_CHOICE["items"] else "")
            if not url:
                return {"ok": False, "reply": "Quelle vidéo ? Cherche-la "
                        "d'abord sur YouTube", "final": "", "detail": ""}
            txt = yt_mode.resume_video(url)
            return {"ok": bool(txt), "reply": txt or "Pas de sous-titres "
                    "disponibles pour cette vidéo", "final": url[:60],
                    "detail": "résumé"}
        if kind == "trend":
            res = yt_mode.tendances(arg)
            if not res:
                return {"ok": False, "reply": "Les tendances ne répondent pas",
                        "final": "", "detail": ""}
            PENDING_CHOICE.update(items=[r["url"] for r in res], t=time.time())
            lignes = " ; ".join(f"{i + 1}. {r['titre']}"
                                for i, r in enumerate(res))
            return {"ok": True, "reply": "Tendances : " + lignes,
                    "final": arg or "toutes", "detail": "mostPopular FR"}
        if kind == "channel":
            info = yt_mode.infos_chaine(arg)
            if not info:
                return {"ok": False, "reply": f"Chaîne « {arg} » introuvable",
                        "final": arg, "detail": ""}
            return {"ok": True,
                    "reply": f"{info['nom']} : {info['abonnes']} abonnés, "
                             f"{info['videos']} vidéos, {info['vues']} vues",
                    "final": info["nom"], "detail": "channels"}
        if kind == "last":
            res = yt_mode.dernieres_videos(arg, 3)
            if not res:
                return {"ok": False, "reply": f"Rien trouvé pour la chaîne « {arg} »",
                        "final": arg, "detail": ""}
            PENDING_CHOICE.update(items=[r["url"] for r in res], t=time.time())
            lignes = " ; ".join(f"{i + 1}. {r['titre']}"
                                for i, r in enumerate(res))
            return {"ok": True, "reply": f"Dernières vidéos de {arg} : " + lignes,
                    "final": arg, "detail": "order=date"}
    except Exception as e:
        core.log_err("youtube " + kind, e)
        return {"ok": False, "reply": "YouTube ne répond pas", "final": arg,
                "detail": str(e)[:80]}
    return {"ok": False, "reply": "Commande YouTube inconnue", "final": "", "detail": ""}


def _do_yt_choice(idx, _body, _raw):
    items = PENDING_CHOICE["items"]
    if not items:
        return {"ok": False, "reply": "Il n'y a plus de résultats en attente",
                "final": "", "detail": ""}
    i = int(idx)
    url = items[i] if -len(items) <= i < len(items) else items[0]
    PENDING_CHOICE["items"] = []
    webbrowser.open(url)
    return {"ok": True, "reply": "C'est parti", "final": url, "detail": "choix vocal"}


def _do_spotify_ctx(kind, name, _raw):
    """Playlist/album/artiste nommés : API Spotify (compte relié) →
    pilotage clavier de l'appli (repli JARVIS) → recherche web."""
    if integrations.spotify_connected():
        try:
            played = integrations.spotify_play_item(name, kind)
            if played:
                labels = {"playlist": "la playlist", "album": "l'album",
                          "artist": "l'artiste"}
                return {"ok": True,
                        "reply": f"Je lance {labels.get(kind, '')} {played}",
                        "final": played, "detail": "spotify api"}
        except Exception as e:
            core.log_err("spotify_ctx", e)
    try:
        if winext.spotify_ui_search_play(name):
            return {"ok": True, "reply": f"Spotify cherche « {name} » — "
                    "je lance le premier résultat", "final": name,
                    "detail": "pilotage clavier"}
    except Exception as e:
        core.log_err("spotify_ui", e)
    webbrowser.open("https://open.spotify.com/search/"
                    + urllib.parse.quote(name))
    return {"ok": True, "reply": f"« {name} » sur Spotify", "final": name,
            "detail": "web"}


def _do_sport(kind, arg, _raw):
    import webinfo
    try:
        if kind == "table":
            res = webinfo.classement(arg)
        elif kind == "next":
            res = webinfo.prochain_match(arg)
        else:
            res = webinfo.resultats_equipe(arg)
    except Exception as e:
        core.log_err("sport", e)
        res = None
    if not res:
        # équipe/ligue inconnue de TheSportsDB → l'IA tentera (rattrapage)
        return {"ok": False, "reply": f"Je n'ai pas trouvé « {arg} » côté sport",
                "final": arg, "detail": "thesportsdb"}
    return {"ok": True, "reply": res.get("reply", "Voilà"), "final": arg,
            "detail": "thesportsdb"}


def _do_iptv(chaine, _body, _raw):
    import iptv
    src = (core.CFG.get("iptv") or {}).get("source", "")
    try:
        if not iptv.chaines():
            iptv.charge_playlist(src)
        if not chaine:
            liste = iptv.chaines()[:8]
            noms = ", ".join(c["nom"] for c in liste)
            return {"ok": True, "reply": f"Chaînes disponibles : {noms}. "
                    "Dis « zappe sur » suivi du nom", "final": "",
                    "detail": f"{len(iptv.chaines())} chaînes"}
        c = iptv.trouve_chaine(chaine)
        if not c:
            return {"ok": False, "reply": f"Chaîne « {chaine} » introuvable",
                    "final": chaine, "detail": ""}
        webbrowser.open(iptv.stream_url(c))
        return {"ok": True, "reply": f"Je mets {c['nom']}", "final": c["nom"],
                "detail": c["url"][:60]}
    except Exception as e:
        core.log_err("iptv", e)
        return {"ok": False, "reply": "La télé n'a pas répondu (playlist "
                "IPTV dans Réglages > Système)", "final": chaine,
                "detail": str(e)[:80]}


def _do_obsidian(target, body, _raw):
    import obsidian
    kind, _, arg = target.partition(":")
    try:
        if kind == "create":
            ok, msg = obsidian.creer_note(arg, body or "")
            return {"ok": ok, "reply": msg, "final": arg, "detail": "obsidian"}
        if kind == "read":
            ok, msg = obsidian.lire_note(arg)
            return {"ok": ok, "reply": msg[:400] if ok else msg,
                    "final": arg, "detail": "obsidian"}
        if kind == "del":
            ok, msg = obsidian.supprimer_note(arg)
            return {"ok": ok, "reply": msg, "final": arg, "detail": "obsidian"}
        if kind == "list":
            notes = obsidian.lister_notes(10)
            if not notes:
                return {"ok": True, "reply": "Ton coffre Obsidian est vide",
                        "final": "0", "detail": obsidian.vault_path()}
            noms = " ; ".join(nt["titre"] for nt in notes)
            return {"ok": True, "reply": f"{len(notes)} notes : {noms}",
                    "final": str(len(notes)), "detail": "obsidian"}
        if kind == "search":
            hits = obsidian.chercher(arg)
            if not hits:
                return {"ok": False, "reply": f"Rien sur « {arg} » dans Obsidian",
                        "final": arg, "detail": ""}
            t0, ex = hits[0]
            return {"ok": True,
                    "reply": f"Trouvé dans « {t0} » : {ex}"
                             + (f" (et {len(hits) - 1} autres)" if len(hits) > 1 else ""),
                    "final": t0, "detail": f"{len(hits)} notes"}
    except Exception as e:
        core.log_err("obsidian", e)
    return {"ok": False, "reply": "Obsidian n'a pas répondu", "final": "", "detail": ""}


def _do_uninstall(query, _body, _raw):
    import uninstall_mode
    if query == "@list":
        progs = uninstall_mode.list_programs()
        noms = " ; ".join(p["nom"] for p in progs[:10])
        return {"ok": True, "reply": f"{len(progs)} programmes installés. "
                f"Les premiers : {noms}", "final": str(len(progs)),
                "detail": "registre"}
    p = uninstall_mode.find_program(query)
    if not p:
        return {"ok": False, "reply": f"Je ne trouve pas « {query} » dans "
                "les programmes installés", "final": query, "detail": ""}
    ok = uninstall_mode.uninstall(p)
    return {"ok": ok,
            "reply": f"Le désinstallateur officiel de {p['nom']} est ouvert — "
                     "confirme dans sa fenêtre" if ok
            else f"Impossible de lancer le désinstallateur de {p['nom']}",
            "final": p["nom"], "detail": p["id"]}


def _do_antivirus(_target, _body, _raw):
    def scan():
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "Start-MpScan -ScanType QuickScan"],
                capture_output=True, timeout=1800, creationflags=0x08000000)
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "@(Get-MpThreatDetection).Count"],
                capture_output=True, text=True, timeout=30,
                creationflags=0x08000000)
            try:
                n = int((r.stdout or "0").strip().splitlines()[-1])
            except Exception:
                n = 0
            msg = ("Analyse antivirus terminée : aucune menace" if n == 0
                   else f"Analyse terminée : {n} détection{'s' if n > 1 else ''}"
                        " — ouvre Sécurité Windows")
        except Exception as e:
            core.log_err("antivirus", e)
            msg = "L'analyse antivirus n'a pas abouti"
        if av_notify:
            try:
                av_notify(msg)
            except Exception:
                pass
    threading.Thread(target=scan, daemon=True).start()
    return {"ok": True, "reply": "Analyse rapide Windows Defender lancée — "
            "je te préviens à la fin", "final": "scan", "detail": "QuickScan"}


def _do_gdoc(kind, arg, _raw):
    if not integrations.google_connected():
        url = {"create": "https://docs.new", "sheet": "https://sheets.new"} \
            .get(kind)
        if url:
            webbrowser.open(url)
            return {"ok": True, "reply": "J'ouvre un document vierge (connecte "
                    "ton compte Google pour la création nommée à la voix)",
                    "final": kind, "detail": "non connecté"}
        return {"ok": False, "reply": "Connecte ton compte Google "
                "(Réglages > Comptes) pour dicter dans un doc",
                "final": "", "detail": "non connecté"}
    try:
        if kind == "create":
            url = integrations.gdoc_create(arg or "Document Nova")
            webbrowser.open(url)
            return {"ok": True, "reply": f"Document « {arg or 'Nova'} » créé",
                    "final": arg, "detail": url}
        if kind == "append":
            ok = integrations.gdoc_append(arg)
            return {"ok": ok, "reply": "Ajouté au document" if ok
                    else "Aucun document en cours — crée d'abord un doc",
                    "final": arg[:60], "detail": "append"}
        if kind == "sheet":
            url = integrations.gsheet_create(arg or "Feuille Nova")
            if url:
                webbrowser.open(url)
            return {"ok": bool(url),
                    "reply": f"Tableur « {arg or 'Nova'} » créé" if url
                    else "La création du tableur a échoué",
                    "final": arg, "detail": url}
    except Exception as e:
        core.log_err("gdoc", e)
        return {"ok": False, "reply": "Google Docs n'a pas répondu — si le "
                "compte date d'avant cette version, reconnecte-le "
                "(nouveaux droits)", "final": "", "detail": str(e)[:80]}
    return {"ok": False, "reply": "Commande document inconnue", "final": "", "detail": ""}


def _do_agenda(_target, _body, _raw):
    if not integrations.google_connected():
        webbrowser.open(SITES["agenda"])
        return {"ok": True, "reply": "J'ouvre ton agenda (connecte ton compte "
                "Google pour que je te le lise)", "final": "web",
                "detail": "non connecté"}
    try:
        events = integrations.gcal_events(5)
    except Exception as e:
        return {"ok": False, "reply": "L'agenda ne répond pas — reconnecte "
                "ton compte Google (nouveaux droits agenda)",
                "final": "", "detail": str(e)[:80]}
    if not events:
        return {"ok": True, "reply": "Rien de prévu à ton agenda",
                "final": "0", "detail": "gcal"}
    parts = []
    for e in events[:3]:
        d = e["debut"]
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            quand = f"{_JOURS[dt.weekday()]} {dt.day} à {dt.hour} h {dt.minute:02d}" \
                if "T" in d else f"{_JOURS[dt.weekday()]} {dt.day}"
        except Exception:
            quand = d
        parts.append(f"{e['titre']} {quand}")
    return {"ok": True, "reply": f"{len(events)} événements : " + " ; ".join(parts),
            "final": str(len(events)), "detail": "gcal"}


def _do_screenshot(_target, _body, _raw):
    try:
        from PIL import ImageGrab
        dest = files_mode.resolve_folder("bureau") or os.path.expanduser("~")
        name = "nova_capture_" + time.strftime("%Y%m%d_%H%M%S") + ".png"
        path = os.path.join(dest, name)
        ImageGrab.grab().save(path)
        return {"ok": True, "reply": f"Capture enregistrée sur le Bureau ({name})",
                "final": name, "detail": path}
    except Exception as e:
        return {"ok": False, "reply": "La capture a échoué", "final": "",
                "detail": str(e)[:80]}


# ------------------------------------------------- minuteurs & rappels ------

def _do_timer(target, body, _raw):
    secs = timers.parse_duration(target)
    if not secs:
        return {"ok": False, "reply": "Je n'ai pas compris la durée",
                "final": target, "detail": "durée illisible"}
    core.start_timer(secs, body)
    h = timers.human(secs)
    reply = f"Je te rappelle « {body} » dans {h}" if body else f"Minuteur lancé : {h}"
    return {"ok": True, "reply": reply, "final": body or h,
            "detail": f"{secs} s" + (" + onglet" if core.CFG.get("timer_style", "web") == "web" else "")}


def _do_timer_cancel(_target, _body, _raw):
    n = timers.cancel_all()
    if not n:
        return {"ok": False, "reply": "Aucun minuteur en cours", "final": "", "detail": ""}
    return {"ok": True,
            "reply": "Minuteur annulé" if n == 1 else f"{n} minuteurs annulés",
            "final": "", "detail": f"{n} annulés"}


# --------------------------------------------------------- heure & météo ----

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre"]


def _do_time(_target, body, _raw):
    now = datetime.now()
    if "jour" in body or "date" in body:
        reply = f"Nous sommes {_JOURS[now.weekday()]} {now.day} {_MOIS[now.month - 1]}"
    else:
        reply = f"Il est {now.hour} h {now.minute:02d}"
    return {"ok": True, "reply": reply, "final": reply, "detail": "horloge"}


def _do_weather(city, _body, _raw):
    if not integrations.is_online():
        return {"ok": False, "reply": "Impossible : pas de connexion internet",
                "final": city, "detail": "hors ligne"}
    try:
        w = integrations.weather(city)
    except Exception as e:
        return {"ok": False, "reply": "La météo ne répond pas, réessayez",
                "final": city, "detail": str(e)[:80]}
    place = w["city"] or city or "ici"
    reply = f"{w['desc']}, {w['temp']} degrés à {place}"
    try:
        if w["feels"] and abs(int(w["feels"]) - int(w["temp"])) >= 3:
            reply += f" (ressenti {w['feels']})"
    except (TypeError, ValueError):
        pass
    return {"ok": True, "reply": reply, "final": place, "detail": "wttr.in"}


# ------------------------------------------------------- musique & agenda ---

def _do_music(query, service, _raw):
    if service == "spotify" and integrations.spotify_connected():
        # compte relié : lecture RÉELLE sur l'appareil Spotify actif
        try:
            played = integrations.spotify_play(query)
            if played:
                return {"ok": True, "reply": f"Je joue {played}",
                        "final": played, "detail": "spotify api"}
        except Exception as e:
            core.log_err("spotify_play", e)
        # pas d'appareil actif / API en panne : on retombe sur le web
    q = urllib.parse.quote(query)
    urls = {
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "youtube music": f"https://music.youtube.com/search?q={q}",
        "spotify": f"https://open.spotify.com/search/{q}",
        "deezer": f"https://www.deezer.com/search/{q}",
    }
    webbrowser.open(urls[service])
    return {"ok": True, "reply": f"« {query} » sur {service.title()}",
            "final": query, "detail": urls[service]}


def _parse_when_fr(text):
    """Extrait (datetime|None, titre) d'une phrase du type
    « dentiste demain à 15 h 30 ». Best-effort, sans dépendance."""
    t = " " + text + " "
    now = datetime.now()
    date = None
    hour, minute = None, 0

    m = re.search(r"\bapres[- ]demain\b", t)
    if m:
        date = now + timedelta(days=2)
        t = t.replace(m.group(0), " ")
    elif re.search(r"\bdemain\b", t):
        date = now + timedelta(days=1)
        t = re.sub(r"\bdemain\b", " ", t)
    elif re.search(r"\baujourd'?hui\b", t):
        date = now
        t = re.sub(r"\baujourd'?hui\b", " ", t)
    elif re.search(r"\bce soir\b", t):
        date, hour = now, 20
        t = re.sub(r"\bce soir\b", " ", t)
    elif re.search(r"\bce midi\b", t):
        date, hour = now, 12
        t = re.sub(r"\bce midi\b", " ", t)
    else:
        for i, j in enumerate(_JOURS):
            m = re.search(rf"\b{j}\b", t)
            if m:
                delta = (i - now.weekday()) % 7 or 7
                date = now + timedelta(days=delta)
                t = t.replace(m.group(0), " ")
                break

    m = re.search(r"\ba (\d{1,2})\s*h(?:eures?)?\s*(\d{1,2})?\b", t)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        t = t[:m.start()] + t[m.end():]
        if date is None:
            date = now if (hour, minute) > (now.hour, now.minute) else now + timedelta(days=1)

    title = re.sub(r"\s+", " ", t).strip(" ,.:-")
    title = re.sub(r"^(?:pour|le|la|un|une)\s+", "", title).strip()
    if date is not None:
        dt = date.replace(hour=hour if hour is not None else 9,
                          minute=minute, second=0, microsecond=0)
        return dt, title
    return None, title


def _do_calendar(rest, _body, _raw):
    dt, title = _parse_when_fr(rest)
    title = title or "Événement Nova"
    url = ("https://calendar.google.com/calendar/render?action=TEMPLATE&text="
           + urllib.parse.quote(title))
    if dt:
        url += ("&dates=" + dt.strftime("%Y%m%dT%H%M%S") + "/"
                + (dt + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S"))
    webbrowser.open(url)
    when = f" {_JOURS[dt.weekday()]} à {dt.hour} h {dt.minute:02d}" if dt else ""
    return {"ok": True, "reply": f"Rendez-vous « {title} »{when} prêt — validez dans l'agenda",
            "final": title, "detail": url}


def _do_emergency(_target, _body, raw):
    cfg = core.CFG.get("modes", {}).get("emergency", {})
    phone = cfg.get("contact_phone", "")
    name = cfg.get("contact_name", "") or "le contact d'urgence"
    if not phone:
        return {"ok": False, "reply": "Aucun contact d'urgence configuré dans les réglages",
                "final": raw, "detail": "contact urgence manquant"}
    lat, lon = winext.tts_bridge.geolocate()
    pos = (f"Position : https://maps.google.com/?q={lat},{lon}"
           if lat is not None else "Position inconnue.")
    who = (active_profile() or {}).get("name", "l'utilisateur")
    sms = f"URGENCE — Message automatique de Nova envoyé par {who}. {pos}"
    if not integrations.twilio_ready(core.CFG):
        return {"ok": False,
                "reply": f"Urgence : Twilio n'est pas configuré, impossible d'alerter {name}",
                "final": sms, "detail": "twilio non configuré"}
    results = []
    try:
        integrations.send_sms(core.CFG, phone, sms)
        results.append("SMS envoyé")
    except Exception as e:
        results.append(f"SMS échec : {e}")
    try:
        say = (f"Message d'urgence automatique de {who}. "
               + ("Une position GPS a été envoyée par SMS." if lat is not None else ""))
        integrations.place_call(core.CFG, phone, say)
        results.append("appel lancé")
    except Exception as e:
        results.append(f"appel échec : {e}")
    ok = any("échec" not in r for r in results)
    return {"ok": ok,
            "reply": (f"Urgence déclenchée, {name} est alerté" if ok
                      else "Urgence : l'alerte n'a pas pu partir"),
            "final": sms, "detail": " ; ".join(results)}


def _do_system(target, _body, _raw):
    profiles = storage.list_profiles()
    nxt = None
    if target:
        q = core.normalize(target)
        nxt = next((p for p in profiles if q in core.normalize(p["name"])), None)
    if not nxt:
        cur = core.CFG.get("active_profile", "")
        idx = next((i for i, p in enumerate(profiles) if p["id"] == cur), -1)
        nxt = profiles[(idx + 1) % len(profiles)]
    core.save_config({"active_profile": nxt["id"]})
    return {"ok": True, "reply": f"Profil actif : {nxt['name']}",
            "final": nxt["name"], "detail": "profil"}
