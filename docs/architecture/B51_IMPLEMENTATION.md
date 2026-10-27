# B5.1 — journal d'implémentation

Base : `a4cb1411cbd10c1f03c2c00dc031ba8925bf9322` sur `main`, incluant les
merges PR #1, #2 et #3. Branche locale `feat/webui-control-plane-b51`, déjà
présente à cette base et sélectionnée sans modification préexistante à déplacer.
Aucun push, merge ou déploiement autorisé/réalisé dans ce chantier.

## B5.1a — fondations

IMPLÉMENTÉ : package `control_plane`, contrats versionnés Mission, Task, Attempt,
ExecutionResult, WorkspaceReference et AuditEvent ; services métier séparés des
routes ; index SQLite propre à l'application ; migration versionnée avec empreinte ;
permissions propriétaire/projet et identités admin/worker distinctes ; création de
brouillons, lecture et audit ; identifiants d'opération UUID idempotents.

Choix : bibliothèque standard Python, sans paquet tiers ni CDN, afin de conserver
une démo reproductible sans installation pip. CPython 3.11–3.13/POSIX visés,
Debian 13 visé ; la version réellement testée sera consignée en validation finale.
`control_plane/requirements.txt` déclare cette absence de dépendances tierces.
Le module SQLite fourni par Python est utilisé avec transactions explicites,
`foreign_keys=ON`, `synchronous=FULL` et un seul backend par répertoire verrouillé.
Les données POC PostgreSQL/SurrealDB et le Discovery Cache sont entièrement séparés.

Licences et références officielles consultées le 27 octobre 2026 :
[Python PSF-2.0 et notices incorporées](https://docs.python.org/3.13/license.html),
[SQLite domaine public](https://www.sqlite.org/copyright.html),
[sqlite3 et transactions](https://docs.python.org/3.13/library/sqlite3.html).
Ces composants n'imposent pas de changement de la licence Apache-2.0 du code
Pepeuch ; aucune distribution de runtime tiers n'est réalisée ici.

HTTP : adaptateur `http.server` borné, limité au loopback. La
[documentation officielle](https://docs.python.org/3.13/library/http.server.html)
ne recommande pas ce module en production : B5.1 reste un prototype local,
pas un serveur LAN prêt à exposer. Host/Origin vérifiés, pas de CORS ni cookies,
authentification Bearer obligatoire pour toutes les routes API, deux secrets
aléatoires locaux privés, aucune valeur codée en dur. Une interface publique
statique pourra charger le formulaire d'authentification, sans données privées.

TESTÉ à ce checkpoint : 15 tests B5.1, 272 tests historiques initiaux inchangés.
Les lots suivants ajouteront l'exécution simulée, les objets persistants et l'UI.
