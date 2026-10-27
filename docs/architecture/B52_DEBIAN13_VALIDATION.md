# B5.2 — préparation de validation Debian 13 / Python 3.13

**Procédure préparée, non exécutée sur la VM existante.** Aucun paquet, driver,
Docker, service système, pare-feu, POC ou configuration Proxmox modifié par B5.2.
L'environnement effectivement testé reste Python 3.12.3 / SQLite 3.45.1 sur Linux.

## Préparer un environnement distinct et autorisé

Employer une machine jetable ou un checkout isolé déjà autorisé, avec Python 3.13
et SQLite disponibles. Ne pas utiliser `/opt/pepeuch-ai/data` ni les volumes POC.
Le lot reste local : ne pas supposer que la branche B5.2 a été poussée. Transférer
le code/fixtures d'un commit local revu (archive Git de fichiers suivis ou copie
de checkout), sans données, secrets, profils navigateur ou sauvegardes privées.
Consigner le SHA exact transféré. Aucune installation automatique si une dépendance
manque : documenter cette étape comme non vérifiée et garder la VM inchangée.

Dans ce checkout isolé, vérifier sans privilège :

```bash
python3.13 --version
python3.13 -c 'import sqlite3; print(sqlite3.sqlite_version)'
```

Aucun paquet pip tiers n'est requis ; SQLite >= 3.31.0 est exigé pour le contrôle
`trusted_schema`. Socket loopback nécessaire pour les tests
HTTP ; aucun appel fournisseur, SDK réel, réseau externe, poids ou GPU.

## Rejouer les tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3.13 -m unittest discover -s tests/control_plane -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3.13 -m unittest discover -s database/poc -p 'test_*.py' -q
git diff --check
```

Résultat attendu au checkpoint : 123 tests Control Plane + 272 tests Discovery
Cache, sans omission ni adaptation des tests historiques. Consigner résultats,
versions runtime/SQLite et refus éventuels de sockets. Les tests utilisent leurs
propres temporaires, jamais les données de la VM. Le fichier de référence B3.3
doit garder SHA256 `ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.

## Démonstration isolée et sauvegarde

Créer un répertoire temporaire privé neuf :

```bash
export PEPEUCH_B52_CHECK_DIR="$(mktemp -d /tmp/pepeuch-b52-check.XXXXXX)"
python3.13 -m control_plane init --data-dir "$PEPEUCH_B52_CHECK_DIR/source"
python3.13 -m control_plane serve --data-dir "$PEPEUCH_B52_CHECK_DIR/source" --port 8765
```

Si ce port est occupé, choisir un autre port local libre explicitement et le
reporter dans l'URL du worker ; ne pas arrêter le service occupant. La commande
n'accepte aucun bind LAN. Ne pas exposer via reverse proxy dans cette procédure.

Dans un autre terminal, avec le même chemin, exécuter le parcours B5.1 : clé admin
locale, brouillon, approbation et worker `--once`. Consigner le SHA du livrable.
Arrêter les processus de cette démo, puis :

```bash
python3.13 -m control_plane backup --data-dir "$PEPEUCH_B52_CHECK_DIR/source" --destination "$PEPEUCH_B52_CHECK_DIR/backup"
python3.13 -m control_plane restore --backup-dir "$PEPEUCH_B52_CHECK_DIR/backup" --data-dir "$PEPEUCH_B52_CHECK_DIR/restored"
python3.13 -m control_plane serve --data-dir "$PEPEUCH_B52_CHECK_DIR/restored" --port 8765
```

Employer la **nouvelle** clé admin du répertoire restauré ; retélécharger le même
fichier/version et comparer SHA256. Vérifier que l'ancien credential worker est
refusé et que le registre indique révoqué. Réactiver uniquement via la procédure
explicite du journal B5.2, backend arrêté, puis tester sa nouvelle clé.

Avec Firefox et geckodriver **déjà présents** dans cet environnement, le scénario
`tests/browser_b51.py` peut être relancé avec les chemins de ces binaires et
Python 3.13. Ne pas les installer automatiquement ; une absence ne valide pas
le navigateur. Aucun profil personnel n'est utilisé. Consigner séparément cette
validation et les tests Python.

À la fin, arrêter uniquement les processus lancés pour la démo et conserver les
artefacts privés jusqu'à revue. Aucun nettoyage global, aucune suppression de
données existantes. Une future suppression doit viser uniquement le répertoire
temporaire nommé ci-dessus, après inspection et confirmation de son propriétaire.
