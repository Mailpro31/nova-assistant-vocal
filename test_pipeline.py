# -*- coding: utf-8 -*-
"""Test rapide du pipeline sans micro : règles + transcription d'un audio synthétique."""
import sys

import main


def test_rules():
    cases = [
        ("Ouvre Google", "open_url", "https://www.google.com"),
        ("Lance Spotify s'il te plaît", "open_app", "spotify:"),
        ("Cherche recette de crêpes", "web_search", None),
        ("Ouvre la calculatrice", "open_app", "calc"),
        ("Va sur ma dernière vidéo YouTube que j'ai regardée hier", None, None),  # -> IA
    ]
    ok = True
    for text, action, target in cases:
        r = main.interpret_rules(text)
        got = (r or {}).get("action"), (r or {}).get("target")
        expected_action = action
        if expected_action is None:
            passed = r is None
        else:
            passed = r is not None and r["action"] == action and (target is None or r["target"] == target)
        print(("PASS" if passed else "FAIL"), repr(text), "->", got)
        ok = ok and passed
    return ok


def test_whisper():
    import numpy as np
    print("Chargement du modèle Whisper (téléchargement au premier lancement)...")
    model = main.get_model()
    # 1 seconde de silence : doit produire une transcription vide sans planter
    audio = np.zeros(16000, dtype=np.float32)
    segments, info = model.transcribe(audio, language="fr")
    text = " ".join(s.text for s in segments).strip()
    print("Transcription du silence:", repr(text))
    print("Modèle OK, langue détectée:", info.language)
    return True


if __name__ == "__main__":
    ok = test_rules()
    if "--whisper" in sys.argv:
        ok = test_whisper() and ok
    print("RESULT:", "OK" if ok else "ECHEC")
    sys.exit(0 if ok else 1)
