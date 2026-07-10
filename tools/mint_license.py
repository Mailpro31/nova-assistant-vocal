# -*- coding: utf-8 -*-
"""Outil ÉDITEUR : génère la paire de clés et signe des licences Nova.

⚠️ NE PAS distribuer. La clé privée (`license_private.pem`, gitignorée) reste
chez l'éditeur ; c'est elle qui rend les licences infalsifiables.

Prérequis : pip install cryptography

Usage :
  python tools/mint_license.py genkey
      Crée license_private.pem et affiche la clé publique à coller dans
      licensing.PUBLIC_KEY_B64 (à faire UNE fois, avant de compiler la release).

  python tools/mint_license.py mint --tier pro --email client@ex.com --days 365
      Affiche une clé de licence « NOVA1.… » à envoyer au client.
      --days 0 (défaut) = licence perpétuelle.

  python tools/mint_license.py mint --tier business --email equipe@ex.com \
      --seats 10 --days 365
      Licence équipe (multi-postes). --seats = nombre de sièges.
"""

import argparse
import base64
import json
import os
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRIV_PATH = os.path.join(os.path.dirname(__file__), os.pardir,
                         "license_private.pem")


def _b64url(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def genkey():
    if os.path.exists(PRIV_PATH):
        print("license_private.pem existe déjà — refus d'écraser "
              "(supprime-le d'abord si tu veux vraiment régénérer).")
        return
    priv = Ed25519PrivateKey.generate()
    with open(PRIV_PATH, "wb") as f:
        f.write(priv.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()))
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw)
    print("Clé privée écrite :", os.path.abspath(PRIV_PATH))
    print("\nColle ceci dans licensing.py :\n")
    print('PUBLIC_KEY_B64 = "%s"' % _b64url(pub))


def mint(tier, email, days, seats):
    with open(PRIV_PATH, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)
    exp = 0 if days <= 0 else int(time.time()) + days * 86400
    payload = json.dumps({"t": tier, "e": email, "x": exp, "s": max(1, seats)},
                         separators=(",", ":"), sort_keys=True).encode("utf-8")
    print("NOVA1.%s.%s" % (_b64url(payload), _b64url(priv.sign(payload))))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Générateur de licences Nova")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("genkey", help="génère la paire de clés")
    m = sub.add_parser("mint", help="signe une licence")
    m.add_argument("--tier", required=True,
                   choices=["free", "pro", "ultra", "business"])
    m.add_argument("--email", required=True)
    m.add_argument("--days", type=int, default=0)
    m.add_argument("--seats", type=int, default=1, help="sièges (Business)")
    a = ap.parse_args()
    genkey() if a.cmd == "genkey" else mint(a.tier, a.email, a.days, a.seats)
