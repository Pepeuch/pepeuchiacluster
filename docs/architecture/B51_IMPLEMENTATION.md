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

## B5.1b — exécution séparée

IMPLÉMENTÉ : `ExecutionManager` pour les tâches, tentatives et baux ; interface
`Coordinator` et plan consultable ; interface `Executor` et worker déterministe.
SIMULÉ : rôle `demo-report`, capacité déclarée `demo.report.v1`, worker `fake-cpu`.
Aucun modèle, matériel GPU ou benchmark n'est associé à cette déclaration.

L'approbation explicite journalise `draft → approved → queued` en une transaction.
Réclamer une tâche crée une tentative/génération nouvelles et passe à `running`.
Le worker n'exécute que la transformation texte prévue, sans outil ou interpréteur.
`failed`/`interrupted` ne sont repris qu'après une demande explicite. L'annulation
active devient `cancel_requested`, puis `cancelled` après accusé du worker ; une
expiration ou un redémarrage clôture la tentative comme `interrupted` et refuse
ses résultats tardifs. Un redémarrage ne réexécute aucune tâche de lui-même.

TESTÉ : 30 tests B5.1 cumulés, dont transitions, double approbation/réclamation,
capacité d'une seule tâche active, échec/interruption/annulation, expiration,
générations, absence de réseau/shell/attente et refus de terminer sans publication.
La publication durable réussie sera raccordée et testée dans B5.1c.

## B5.1c — objets et workspaces persistants

IMPLÉMENTÉ : upload borné, références logiques fichier/version, SHA256 vérifié,
versions immuables, téléchargement en pièce jointe, audit et quotas cumulés sur
toutes les versions. Noms ASCII plats, comparés sans distinction de casse ; refus
des chemins, noms réservés et caractères de contrôle. Limites par défaut : 1 Mio
par fichier, 16 Mio par workspace, 100 fichiers et 100 versions par fichier.
Les fichiers autorisés d'une mission désignent des versions figées, pas un chemin.

La publication crée un temporaire privé, vérifie les octets du staging, fsync le
fichier, renomme l'objet par son empreinte et fsync le répertoire ; l'index, le
résultat, l'audit et `completed` sont ensuite commités ensemble dans SQLite.
Une erreur avant commit laisse les anciennes versions intactes. Un crash peut
laisser un objet non référencé : il n'est pas visible comme livrable et n'est pas
supprimé automatiquement. Les résidus staging d'un autre processus sont ignorés.
La répétition exacte d'une réponse acceptée est acquittée sans nouvelle version.

TESTÉ : 51 tests B5.1 cumulés, avec succès complet puis redémarrage, download et
SHA identiques, conflit de version, deux uploads réellement concurrents, quota,
fichier trop grand, staging tronqué, corruption, symlink et interruptions avant
renommage ou après fsync avant commit. Pas de simulation de coupure électrique.
La rétention n'est pas une sauvegarde ; la procédure hors ligne sera documentée
avec les commandes de démonstration dans le dernier lot.
