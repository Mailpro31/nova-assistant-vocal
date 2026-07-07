# -*- coding: utf-8 -*-
"""
Réponses locales hors-ligne (portées de JARVIS, TechEnClair) : blagues,
citations, capitales, monnaies, fuseaux horaires, épellation, calcul mental,
conversions, tirages aléatoires, mot de passe, comptes à rebours.
Données + logique pure — le routage vocal reste dans modes.classify().
"""

import ast
import math
import operator
import random
import re
import string
from datetime import date, datetime

BLAGUES = [
    "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon ils tomberaient dans le bateau !",
    "Un homme entre dans une bibliothèque et demande : avez-vous des livres sur la paranoïa ? La bibliothécaire chuchote : ils sont juste derrière vous.",
    "Qu'est-ce qu'un canif ? Un petit fien.",
    "Pourquoi l'épouvantail a-t-il reçu un prix ? Parce qu'il était exceptionnel dans son domaine.",
    "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël.",
    "Qu'est-ce qu'un crocodile qui surveille la cour d'école ? Un sac à dents.",
    "Pourquoi les mathématiciens confondent-ils Halloween et Noël ? Parce que le 31 octobre égale le 25 décembre, en octal et en décimal.",
    "Un homme entre dans un bar... Aïe.",
    "Qu'est-ce qu'un agneau qui bégaie ? Du bé bé beurre.",
    "Comment on appelle un poisson sans yeux ? Un poisson.",
    "Qu'est-ce qu'un Tic qui tombe d'un arbre ? Un Tac.",
    "Pourquoi le scarabée est-il si fort ? Parce qu'il soulève des bouses de vache.",
    "Comment appelle-t-on un chat qui est tombé dans un pot de confiture ? Un chat confit.",
    "Qu'est-ce qu'un yaourt dans la forêt ? Un yaourt nature.",
    "Pourquoi les girafes ont-elles un long cou ? Parce que leurs pieds sentent mauvais.",
    "Qu'est-ce qu'un os dans un bain de boue ? Sherlock Bones.",
    "Comment appelle-t-on une ceinture en peau de crocodile ? Une ceinture qui fait le tour du ventre.",
    "Qu'est-ce qu'un cactus ? Un arbre bien défendu.",
    "Pourquoi les Belges mettent-ils leur portable au congélateur ? Pour avoir des contacts froids.",
    "Qu'est-ce qu'un philosophe ? Quelqu'un qui cherche dans une pièce noire un chapeau noir qui n'existe pas.",
]

CITATIONS = [
    "Le succès, c'est tomber sept fois et se relever huit. Proverbe japonais.",
    "La vie, c'est comme une bicyclette, il faut avancer pour ne pas perdre l'équilibre. Albert Einstein.",
    "Le seul moyen de faire du bon travail est d'aimer ce que vous faites. Steve Jobs.",
    "Celui qui déplace les montagnes commence par enlever les petites pierres. Confucius.",
    "N'attendez pas. Le moment ne sera jamais parfait. Napoléon Hill.",
    "La plus grande gloire n'est pas de ne jamais tomber, mais de se relever à chaque chute. Nelson Mandela.",
    "Vous ne pouvez pas changer le début, mais vous pouvez commencer là où vous êtes et changer la fin. C.S. Lewis.",
    "Le pessimiste voit la difficulté dans chaque opportunité. L'optimiste voit l'opportunité dans chaque difficulté. Winston Churchill.",
    "Ce n'est pas la montagne que nous conquérons, mais nous-mêmes. Edmund Hillary.",
    "La créativité, c'est l'intelligence qui s'amuse. Albert Einstein.",
    "Chaque expert a un jour été un débutant. Helen Hayes.",
    "Votre temps est limité. Ne le gâchez pas en vivant la vie de quelqu'un d'autre. Steve Jobs.",
    "Le secret pour aller de l'avant, c'est de commencer. Mark Twain.",
    "Les personnes assez folles pour penser qu'elles peuvent changer le monde sont celles qui le font. Apple.",
    "Tout ce que l'esprit peut concevoir et croire, il peut l'accomplir. Napoleon Hill.",
]

PHONETIQUE = {
    "a": "Alpha", "b": "Bravo", "c": "Charlie", "d": "Delta", "e": "Echo",
    "f": "Foxtrot", "g": "Golf", "h": "Hotel", "i": "India", "j": "Juliet",
    "k": "Kilo", "l": "Lima", "m": "Mike", "n": "November", "o": "Oscar",
    "p": "Papa", "q": "Quebec", "r": "Romeo", "s": "Sierra", "t": "Tango",
    "u": "Uniform", "v": "Victor", "w": "Whiskey", "x": "X-ray", "y": "Yankee",
    "z": "Zulu",
}

CAPITALES = {
    "france": "Paris", "espagne": "Madrid", "italie": "Rome", "allemagne": "Berlin",
    "royaume-uni": "Londres", "royaume uni": "Londres", "angleterre": "Londres",
    "portugal": "Lisbonne", "pays-bas": "Amsterdam", "pays bas": "Amsterdam",
    "belgique": "Bruxelles", "suisse": "Berne", "autriche": "Vienne",
    "pologne": "Varsovie", "suede": "Stockholm", "norvege": "Oslo",
    "danemark": "Copenhague", "finlande": "Helsinki", "russie": "Moscou",
    "ukraine": "Kiev", "grece": "Athènes", "turquie": "Ankara",
    "maroc": "Rabat", "algerie": "Alger", "tunisie": "Tunis",
    "egypte": "Le Caire", "senegal": "Dakar", "cameroun": "Yaoundé",
    "cote d'ivoire": "Yamoussoukro", "mali": "Bamako",
    "etats-unis": "Washington", "etats unis": "Washington", "usa": "Washington",
    "canada": "Ottawa", "mexique": "Mexico", "bresil": "Brasilia",
    "argentine": "Buenos Aires", "chili": "Santiago", "perou": "Lima",
    "colombie": "Bogota", "venezuela": "Caracas", "chine": "Pékin",
    "japon": "Tokyo", "coree du sud": "Séoul", "inde": "New Delhi",
    "pakistan": "Islamabad", "australie": "Canberra",
    "nouvelle-zelande": "Wellington", "nouvelle zelande": "Wellington",
    "afrique du sud": "Pretoria", "nigeria": "Abuja", "kenya": "Nairobi",
    "ghana": "Accra", "israel": "Jérusalem", "iran": "Téhéran", "irak": "Bagdad",
    "arabie saoudite": "Riyad", "emirats arabes unis": "Abu Dhabi",
    "qatar": "Doha", "indonesie": "Jakarta", "thailande": "Bangkok",
    "vietnam": "Hanoï", "philippines": "Manille", "malaisie": "Kuala Lumpur",
}

MONNAIES = {
    "france": "l'euro", "espagne": "l'euro", "italie": "l'euro",
    "allemagne": "l'euro", "portugal": "l'euro", "belgique": "l'euro",
    "suisse": "le franc suisse", "royaume-uni": "la livre sterling",
    "royaume uni": "la livre sterling", "angleterre": "la livre sterling",
    "etats-unis": "le dollar américain", "etats unis": "le dollar américain",
    "usa": "le dollar américain", "canada": "le dollar canadien",
    "australie": "le dollar australien", "japon": "le yen", "chine": "le yuan",
    "russie": "le rouble", "inde": "la roupie indienne", "bresil": "le real",
    "maroc": "le dirham marocain", "algerie": "le dinar algérien",
    "tunisie": "le dinar tunisien", "mexique": "le peso mexicain",
    "turquie": "la livre turque", "arabie saoudite": "le riyal saoudien",
    "emirats arabes unis": "le dirham des Émirats", "coree du sud": "le won",
}

FUSEAUX = {
    "new york": ("New York", "America/New_York"),
    "los angeles": ("Los Angeles", "America/Los_Angeles"),
    "chicago": ("Chicago", "America/Chicago"),
    "montreal": ("Montréal", "America/Toronto"),
    "toronto": ("Toronto", "America/Toronto"),
    "london": ("Londres", "Europe/London"),
    "londres": ("Londres", "Europe/London"),
    "berlin": ("Berlin", "Europe/Berlin"),
    "madrid": ("Madrid", "Europe/Madrid"),
    "rome": ("Rome", "Europe/Rome"),
    "moscou": ("Moscou", "Europe/Moscow"),
    "dubai": ("Dubaï", "Asia/Dubai"),
    "inde": ("l'Inde", "Asia/Kolkata"),
    "mumbai": ("Mumbai", "Asia/Kolkata"),
    "delhi": ("Delhi", "Asia/Kolkata"),
    "pekin": ("Pékin", "Asia/Shanghai"),
    "shanghai": ("Shanghai", "Asia/Shanghai"),
    "tokyo": ("Tokyo", "Asia/Tokyo"),
    "japon": ("Tokyo", "Asia/Tokyo"),
    "seoul": ("Séoul", "Asia/Seoul"),
    "sydney": ("Sydney", "Australia/Sydney"),
    "melbourne": ("Melbourne", "Australia/Melbourne"),
    "auckland": ("Auckland", "Pacific/Auckland"),
    "sao paulo": ("São Paulo", "America/Sao_Paulo"),
    "buenos aires": ("Buenos Aires", "America/Argentina/Buenos_Aires"),
    "mexico": ("Mexico", "America/Mexico_City"),
    "honolulu": ("Honolulu", "Pacific/Honolulu"),
    "hawai": ("Hawaï", "Pacific/Honolulu"),
    "bangkok": ("Bangkok", "Asia/Bangkok"),
    "singapour": ("Singapour", "Asia/Singapore"),
    "hong kong": ("Hong Kong", "Asia/Hong_Kong"),
    "le caire": ("Le Caire", "Africa/Cairo"),
    "nairobi": ("Nairobi", "Africa/Nairobi"),
    "johannesburg": ("Johannesburg", "Africa/Johannesburg"),
    "casablanca": ("Casablanca", "Africa/Casablanca"),
    "new delhi": ("New Delhi", "Asia/Kolkata"),
    "vancouver": ("Vancouver", "America/Vancouver"),
    "miami": ("Miami", "America/New_York"),
    "san francisco": ("San Francisco", "America/Los_Angeles"),
    "athenes": ("Athènes", "Europe/Athens"),
    "lisbonne": ("Lisbonne", "Europe/Lisbon"),
    "istanbul": ("Istanbul", "Europe/Istanbul"),
}


def blague():
    return random.choice(BLAGUES)


def citation():
    return random.choice(CITATIONS)


def heure_ville(key):
    """« Quelle heure est-il à Tokyo » → phrase, ou None si ville inconnue."""
    hit = FUSEAUX.get(key.strip())
    if not hit:
        return None
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(hit[1]))
        return f"Il est {now.hour} h {now.minute:02d} à {hit[0]}"
    except Exception:
        return None


def capitale(pays):
    return CAPITALES.get(pays.strip())


def monnaie(pays):
    return MONNAIES.get(pays.strip())


def epelle(mot):
    mot = mot.strip()
    if not mot:
        return None
    return " - ".join(c.upper() if c.isalnum() else c for c in mot)


def otan(lettre):
    c = lettre.strip().lower()[:1]
    nom = PHONETIQUE.get(c)
    return f"{c.upper()} comme {nom}" if nom else None


def pile_ou_face():
    return "Pile !" if random.random() < 0.5 else "Face !"


def de(faces=6):
    return f"Le dé donne {random.randint(1, max(2, faces))}"


def nombre(a=1, b=100):
    a, b = int(a), int(b)
    if a > b:
        a, b = b, a
    return f"{random.randint(a, b)}"


def mot_de_passe(longueur=16):
    """Mot de passe robuste — JAMAIS lu à voix haute ni écrit dans
    l'historique (différence de sécurité volontaire avec JARVIS)."""
    try:
        longueur = int(longueur or 16)
    except (TypeError, ValueError):
        longueur = 16
    n = max(8, min(64, longueur))
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    rng = random.SystemRandom()
    return "".join(rng.choice(alphabet) for _ in range(n))


# --------------------------------------------------------- calcul mental ----

# Évaluateur arithmétique sans eval() : seuls nombres, + - * / ** (unaire
# inclus), parenthèses, sqrt(), pi et e sont autorisés ; tout le reste lève
# une exception (→ repli IA). Remplace un eval() sandboxé pour supprimer toute
# surface d'exécution de code arbitraire, à comportement identique.
_CALC_NAMES = {"pi": math.pi, "e": math.e}
_CALC_FUNCS = {"sqrt": math.sqrt}
_CALC_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow,
}
_CALC_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("constante interdite")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _CALC_BINOPS.get(type(node.op))
        if op is None:
            raise ValueError("opérateur interdit")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _CALC_UNARY.get(type(node.op))
        if op is None:
            raise ValueError("opérateur unaire interdit")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Name):
        if node.id in _CALC_NAMES:
            return _CALC_NAMES[node.id]
        raise ValueError("nom interdit")
    if isinstance(node, ast.Call):
        if (isinstance(node.func, ast.Name) and node.func.id in _CALC_FUNCS
                and len(node.args) == 1 and not node.keywords):
            return _CALC_FUNCS[node.func.id](_eval_node(node.args[0]))
        raise ValueError("appel interdit")
    raise ValueError("expression interdite")


def _safe_eval(expr):
    """Évalue une expression arithmétique restreinte sans eval(). Le strip()
    reproduit la tolérance d'eval() aux espaces de bord : ast.parse(mode="eval")
    lèverait sinon IndentationError sur un espace initial."""
    return _eval_node(ast.parse(expr.strip(), mode="eval").body)


_CALC_PREFIX = re.compile(
    r"^(?:combien (?:font|fait|ca fait|est[- ]ce que ca fait)|ca fait combien"
    r"|calcule(?:[- ]moi)?|quel est le resultat de|quelle est la racine)\s*", re.I)

_CALC_WORDS = [
    (re.compile(r"\bmultiplie(?:s|r)? par\b"), "*"),
    (re.compile(r"\bfois\b"), "*"),
    (re.compile(r"\bdivise(?:s|r)? par\b"), "/"),
    (re.compile(r"\bplus\b"), "+"),
    (re.compile(r"\bmoins\b"), "-"),
    (re.compile(r"\bpuissance\b"), "**"),
    (re.compile(r"\bau carre\b"), "**2"),
    (re.compile(r"\bau cube\b"), "**3"),
    (re.compile(r"\bracine (?:carree )?(?:de |d')"), "sqrt"),
    (re.compile(r"\bvirgule\b"), "."),
    (re.compile(r"\bpour ?cents? de\b"), "/100*"),
]


def calcule(n):
    """« combien font 12 fois 8 », « calcule la racine de 16 » → résultat en
    texte, ou None (→ IA). n = phrase normalisée sans accents."""
    if not _CALC_PREFIX.match(n):
        return None
    expr = _CALC_PREFIX.sub("", n).strip(" ?.!")
    expr = re.sub(r"\b(?:la|le|les|l')\b", " ", expr)   # « la racine de 16 »
    for rx, rep in _CALC_WORDS:
        expr = rx.sub(rep, expr)
    # « x » et « sur » : uniquement ENTRE deux chiffres (jamais globalement —
    # piège JARVIS : « taxi sur paris » deviendrait une division)
    expr = re.sub(r"(\d)\s*x\s*(\d)", r"\1*\2", expr)
    expr = re.sub(r"(\d)\s+sur\s+(\d)", r"\1/\2", expr)
    expr = expr.replace(",", ".")
    if "sqrt" in expr and "(" not in expr:
        expr = re.sub(r"sqrt\s*([\d.]+)", r"sqrt(\1)", expr)
    if not re.fullmatch(r"[0-9+\-*/(). \tsqrtpie]*", expr):
        return None
    if not re.search(r"\d", expr) or not re.search(r"[+\-*/]|sqrt", expr):
        return None
    # garde anti-DoS : l'explosion mémoire d'une puissance géante survient
    # PENDANT eval (le try/except arrive trop tard). On refuse les tours de
    # puissances et les grands exposants AVANT toute évaluation.
    if "**" in expr:
        if expr.count("**") > 1:            # tour : « 9 ** 9 ** 9 »
            return None
        _, _, _exp = expr.partition("**")   # exposant à droite du **
        try:
            if abs(float(_exp)) > 100:      # exposant trop grand
                return None
        except ValueError:
            return None                     # exposant non trivial → IA
    try:
        val = _safe_eval(expr)
    except Exception:
        return None
    if isinstance(val, float):
        val = round(val, 3)
        if val == int(val):
            val = int(val)
    return f"Ça fait {val}"


# ----------------------------------------------------------- conversions ----

def convertit(n):
    """Conversions locales : km↔miles, °C↔°F. Retourne une phrase ou None."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:km|kilometres?)\s+en\s+miles?", n)
    if m:
        v = float(m.group(1).replace(",", "."))
        return f"{m.group(1)} kilomètres font {round(v * 0.621371, 2)} miles"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*miles?\s+en\s+(?:km|kilometres?)", n)
    if m:
        v = float(m.group(1).replace(",", "."))
        return f"{m.group(1)} miles font {round(v / 0.621371, 2)} kilomètres"
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:degres?|°)?\s*(?:celsius|c)\s+en\s+fahrenheit", n)
    if m:
        v = float(m.group(1).replace(",", "."))
        return f"{m.group(1)} degrés Celsius font {round(v * 9 / 5 + 32, 1)} degrés Fahrenheit"
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:degres?|°)?\s*(?:fahrenheit|f)\s+en\s+(?:celsius|c)\b", n)
    if m:
        v = float(m.group(1).replace(",", "."))
        return f"{m.group(1)} degrés Fahrenheit font {round((v - 32) * 5 / 9, 1)} degrés Celsius"
    return None


def convertit_devise(n, taux_live=None):
    """EUR↔USD. taux_live = fonction () -> float ou None (frankfurter).
    Sans taux live : approximation annoncée comme telle (jamais « exact »)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:euros?|€)\s+en\s+(?:dollars?|\$)", n)
    sens = "eur_usd" if m else None
    if not m:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:dollars?|\$)\s+en\s+(?:euros?|€)", n)
        sens = "usd_eur" if m else None
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    taux = None
    if taux_live:
        try:
            taux = taux_live()
        except Exception:
            taux = None
    approx = ""
    if not taux:
        taux = 1.08
        approx = " environ (taux indicatif)"
    out = v * taux if sens == "eur_usd" else v / taux
    unite = "dollars" if sens == "eur_usd" else "euros"
    return f"{m.group(1)} {'euros' if sens == 'eur_usd' else 'dollars'} font " \
           f"{round(out, 2)} {unite}{approx}"


# ----------------------------------------------------- comptes à rebours ----

def compte_a_rebours(n):
    """« Combien de jours avant Noël / le nouvel an » → phrase ou None."""
    today = date.today()
    if "noel" in n:
        cible = date(today.year, 12, 25)
        nom = "Noël"
    elif "nouvel an" in n or "nouvelle annee" in n or "jour de l'an" in n:
        cible = date(today.year + 1, 1, 1)
        nom = "le nouvel an"
    else:
        return None
    if cible < today:
        cible = cible.replace(year=cible.year + 1)
    delta = (cible - today).days
    if delta == 0:
        return f"C'est aujourd'hui, c'est {nom} !"
    return f"Il reste {delta} jour{'s' if delta > 1 else ''} avant {nom}"


# --------------------------------------------------------------- système ----

def sysinfo(kind):
    """batterie / processeur / mémoire / uptime — psutil (déjà dépendance)."""
    import psutil
    if kind == "batterie":
        b = psutil.sensors_battery()
        if not b:
            return "Pas de batterie détectée : ce PC est sur secteur"
        plug = " et en charge" if b.power_plugged else ""
        return f"Batterie à {int(b.percent)} %{plug}"
    if kind == "cpu":
        return f"Le processeur est à {psutil.cpu_percent(interval=0.5):.0f} %"
    if kind == "ram":
        vm = psutil.virtual_memory()
        return (f"Mémoire utilisée : {vm.percent:.0f} % "
                f"({vm.used / (1024 ** 3):.1f} Go sur {vm.total / (1024 ** 3):.0f} Go)")
    if kind == "uptime":
        import time as _t
        up = int(_t.time() - psutil.boot_time())
        h, m = divmod(up // 60, 60)[0], (up // 60) % 60
        return f"Le PC est allumé depuis {h} h {m:02d}"
    return None
