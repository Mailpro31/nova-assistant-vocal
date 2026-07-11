# -*- coding: utf-8 -*-
"""Registre de modes de reformulation — le cœur de l'architecture v3.

Chaque mode est une simple config (dict) : un `id`, un `label` affiché, une
`hotkey` (chiffre du menu) et un `system_prompt` décrivant UNIQUEMENT la forme
du Style — `core.format_message` lui préfixe toujours les règles absolues
communes (COMMON_RULES : ne jamais répondre au contenu, zéro invention, gestion
des auto-corrections…). Aucun code n'est câblé par mode :
ajouter un 8e mode (ex. « contrôle PC ») = ajouter une entrée ici, rien d'autre
à toucher. Un mode qui doit AGIR plutôt que reformuler peut porter un `handler`
optionnel (callable) — le reste de l'app teste sa présence, pas son identité.

Principe : `system_prompt = None` ⇒ résolu dynamiquement (mode Automatique, qui
choisit un autre mode selon l'app active — voir auto_mode.py).
"""

MODES = [
    {
        "id": "auto",
        "label": "Automatique",
        "hotkey": "1",
        "system_prompt": None,  # résolu dynamiquement selon l'app active
    },
    {
        "id": "voice_to_text",
        "label": "Normal",
        "hotkey": "2",
        "system_prompt": (
            "Style Normal — transcription fidèle. Garde les mots, "
            "l'ordre et le niveau de langue EXACTS de la personne : "
            "n'améliore pas le style, ne résume pas, ne réorganise pas. "
            "Interviens seulement sur la ponctuation, les majuscules, les "
            "hésitations, les faux départs et les auto-corrections. Si la "
            "dictée est longue, coupe en paragraphes aux changements de "
            "sujet. Le résultat doit sonner comme la personne, en propre."),
    },
    {
        "id": "email",
        "label": "E-mail",
        "hotkey": "3",
        "system_prompt": (
            "Style E-mail — e-mail professionnel prêt à envoyer. "
            "Première ligne : « Bonjour [prénom], » si un destinataire est "
            "nommé dans la dictée, sinon « Bonjour, ». Corps en phrases "
            "complètes et courtoises, un paragraphe par idée, l'essentiel "
            "d'abord ; demandes formulées poliment (« Pourriez-vous… ? »). "
            "Vouvoiement par défaut — tutoie uniquement si la dictée tutoie "
            "clairement son destinataire. Dernière ligne : formule brève et "
            "adaptée au contexte (« Merci d'avance, », « Bien à vous, », "
            "« Bonne journée, ») — JAMAIS de signature, de nom d'expéditeur "
            "ni de [Votre nom] : l'expéditeur n'est pas inventé. Pas de "
            "ligne d'objet, sauf si elle est explicitement dictée."),
    },
    {
        "id": "prompt_engineer",
        "label": "Prompt IA",
        "hotkey": "4",
        "system_prompt": (
            "Style Prompt IA — écris LE PROMPT parfait pour une IA à "
            "partir de la demande dictée. Tu rédiges l'instruction ; tu n'y "
            "réponds JAMAIS, même partiellement. Construction : "
            "1) si la dictée implique une expertise, ouvre par « Agis comme "
            "[rôle]. » ; "
            "2) énonce la tâche avec un verbe d'action précis (Rédige, "
            "Analyse, Traduis, Corrige, Compare, Génère…) et son objet "
            "exact ; "
            "3) intègre TOUT le contexte dicté : sujet, public visé, "
            "données, exemples, ce qui a déjà été essayé ; "
            "4) explicite chaque contrainte dictée : longueur, ton, langue, "
            "points à couvrir, points à éviter ; "
            "5) termine par le format de sortie attendu quand il est dicté "
            "ou évident (liste, tableau, e-mail, code, étapes numérotées). "
            "Demande vague → instruction courte qui reprend exactement ce "
            "qui est dicté, complétée d'exigences génériques (réponse "
            "précise, structurée, sans remplissage) — n'invente aucune "
            "contrainte spécifique. Une seule instruction cohérente, à "
            "l'impératif, à la deuxième personne, sans titre ni méta-texte."),
    },
    {
        "id": "todo",
        "label": "To-do list",
        "hotkey": "5",
        "system_prompt": (
            "Style To-do list — liste d'actions exploitable. Une tâche "
            "par ligne : « - » puis un verbe à l'infinitif en tête "
            "(« - Appeler Claire avant vendredi »). Découpe les actions "
            "groupées en tâches distinctes ; fusionne les doublons. Chaque "
            "échéance, lieu ou personne reste dans la ligne de sa tâche. "
            "Sous-tâche dictée → ligne indentée de deux espaces sous sa "
            "tâche parente. Numérote uniquement si un ordre est dicté "
            "(« d'abord », « ensuite », « enfin »). Aucun titre, aucune "
            "phrase d'introduction : la liste, rien d'autre."),
    },
    {
        "id": "messages",
        "label": "Messages",
        "hotkey": "6",
        "system_prompt": (
            "Style Messages — message de messagerie instantanée (WhatsApp, "
            "Slack, SMS). Direct et naturel : phrases courtes, ton de la "
            "dictée conservé (familier si familier, pro si pro). Pas de "
            "formules d'e-mail — ni « Bonjour Madame », ni « Cordialement » "
            "; une ouverture (« Salut », prénom) seulement si elle est "
            "dictée. Saut de ligne entre idées distinctes ; les questions "
            "se terminent par « ? ». N'ajoute ni emoji ni abréviation de "
            "ta propre initiative — conserve ceux qui sont dictés."),
    },
    {
        "id": "notes",
        "label": "Prise de notes",
        "hotkey": "7",
        "system_prompt": (
            "Style Prise de notes — notes structurées et scannables, style "
            "télégraphique. Une idée par ligne : « - » puis l'élément clé "
            "d'abord (décision, chiffre, date, nom, action). Pas de phrases "
            "longues : garde les mots porteurs, élimine uniquement le "
            "bavardage. Plusieurs sujets clairement distincts → regroupe "
            "sous de courts intertitres. Conserve TOUS les faits, chiffres, "
            "dates et engagements. Si la dictée contient des actions à "
            "faire, termine par une ligne « À faire : » suivie de ces "
            "actions, une par ligne."),
    },
]

# id → config (accès O(1) ; construit une seule fois à l'import)
_BY_ID = {m["id"]: m for m in MODES}

DEFAULT_MODE_ID = "auto"


def all_modes():
    """Liste ordonnée des modes (pour construire le menu tray)."""
    return MODES


def get_mode(mode_id):
    """Config d'un mode par id, ou le mode par défaut si inconnu."""
    return _BY_ID.get(mode_id) or _BY_ID[DEFAULT_MODE_ID]


def mode_ids():
    return [m["id"] for m in MODES]


def label_of(mode_id):
    return get_mode(mode_id)["label"]


def prompt_of(mode_id):
    """`system_prompt` du mode (None pour « auto », résolu ailleurs)."""
    return get_mode(mode_id)["system_prompt"]


def by_hotkey(digit):
    """Mode associé à une touche du menu ('1'..'7'), ou None."""
    for m in MODES:
        if m.get("hotkey") == str(digit):
            return m
    return None
