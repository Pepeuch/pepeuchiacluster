# B5.2 — sécurisation et résilience

Base : `a822b4d`, merge publié de B5.1 (`a4c537c`) vérifié après fetch. `main`
actualisé par avance rapide uniquement ; branche `feat/webui-control-plane-b52`.
Arbre initial propre, 341 tests de départ réussis. Commits locaux, aucun push.

## B5.2a — HTTP : garanties locales testées

Le parseur accepte un sous-ensemble explicite HTTP/1.0–1.1 : CRLF, GET/POST,
chemin origin-form, aucun doublon d'en-tête, repli, transfert chunked, upgrade ou
Expect. Fermeture après une requête ; HEAD refusé sans corps. Les fichiers
statiques passent les mêmes contrôles de framing/hôte/origine. Erreurs constantes,
sans chemin, corps ou credential ; `no-store` et protections WebUI sur les erreurs
également. Les autorisations B5.1 restent inchangées.

Limites : ligne de requête 2048 octets, ligne d'en-tête 4096, en-têtes cumulés
16384, 32 en-têtes, corps 1 500 000, 16 connexions actives. Deadline absolue de
lecture de 5 secondes, sans remise à zéro à chaque octet. Client worker : réponse
JSON cadrée par une longueur unique, sans compression, 128 Kio maximum ; deadline
de lecture, aucun proxy ou suivi de redirection. Aucun retry implicite.

85 tests Control Plane réussis (69 B5.1 conservés + 16 nouveaux) : wire HTTP,
troncature, ambiguïtés, limites, timeout, saturation/récupération et deadlines
injectées. La première exécution a révélé `flush()` manquant lors d'une fermeture
anticipée du lecteur ; correction validée par le test de redirection existant.

Références officielles : [syntaxe et framing RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html),
[limites de http.server](https://docs.python.org/3.13/library/http.server.html).
Il ne s'agit ni d'une implémentation HTTP générale ni d'une validation production.
Pas de TLS, exposition LAN, reverse proxy, débit garanti ou préemption de logique
métier. Les délais bornent les I/O, pas une fonction métier bloquée.

## B5.2b — sauvegarde/restauration hors ligne

IMPLÉMENTÉ : `backup` et `restore`, explicitement lancés en CLI. Verrou exclusif
de backend obligatoire ; refus d'un journal SQLite/WAL restant à récupérer.
Index en lecture seule, contrôle d'intégrité/FK/schéma connu, références et SHA256
des objets vérifiés. Référence : [sauvegardes SQLite](https://www.sqlite.org/backup.html)
et [contrôles SQLite](https://www.sqlite.org/pragma.html#pragma_integrity_check).

La sauvegarde est un **dossier privé 0700**, pas une archive publiable : SQLite,
les deux fichiers de configuration connus, objets référencés et manifeste versionné.
Secrets, logs, staging et objets orphelins sont exclus, sans suppression côté source.
Les données applicatives peuvent être privées : ne jamais partager ce dossier
comme s'il était expurgé de tout contenu sensible. Les SHA256 détectent une
corruption, pas un remplacement malveillant de tout le manifeste.

La destination doit être inexistante ; création exclusive sans écrasement.
Manifeste de sauvegarde écrit en dernier. À la restauration, validation intégrale
avant création de destination, copie revérifiée, nouvelles clés et marqueur
d'installation écrit en dernier. Une interruption conserve une copie incomplète
privée et refusée ; aucune restauration/prune ou suppression automatique.
Répertoire parent et compte local de confiance supposés, pas de garantie NFS.

TESTÉ : 101 tests Control Plane cumulés (+16) ; mission → worker → publication →
sauvegarde → restauration ailleurs → redémarrage → mêmes IDs, événements, octets
et SHA256. Credentials source absents de la copie et refusés sur la restauration.
Refus de source active, destination existante, schéma modifié, chemins/liens,
index/manifestes/objets corrompus, références invalides et copies interrompues.
Pas de simulation de panne électrique ni de sauvegarde hors machine déjà déployée.

Limites bornées : index 256 Mio, manifeste 4 Mio, au plus 10 003 fichiers décrits
et 2 Gio de contenu. Les backups dépassant le format/les limites sont refusés.
Rétention sans purge. Les workers d'un registre restauré seront révoqués avant
acceptation ; un réenrôlement explicite est requis dans le lot identité.

## B5.2c — identités, révocation et politiques bornées

IMPLÉMENTÉ : registre `worker-identity/v1`, IDs stables locaux au backend, statut
active/revoked, version monotone de credential, SHA256 du credential à haute
entropie (pas sa valeur), capacités et limites fermées. Chaque tentative est liée
à la version de credential lors de son attribution. Secrets nouveaux écrits dans
des fichiers privés immuables, fsync avant commit, jamais dans les réponses HTTP.

Migration **applicative** `0002.sql` : tables additives, association des anciennes
tentatives à l'epoch 1 et préservation des opérations idempotentes worker B5.1.
Le SQL `0001.sql`, IDs et DTO d'exécution v1 restent inchangés ; le champ d'epoch
est interne au principal/registre. Aucun changement du Discovery Cache ou des POC.

Authentification worker relue à chaque requête et autorisation revérifiée dans
la transaction métier **avant tout replay de réponse idempotente**. Une révocation
interrompt les tentatives en cours de ce worker, bloque les nouvelles et refuse
les résultats anciens. Une opération qui a déjà commit avant la révocation reste
un résultat valide : ordre déterminé par la transaction SQLite, pas une préemption.
Les tâches déjà en file restent affectées et non exécutables tant que cette
identité n'est pas réactivée ; l'utilisateur peut les annuler explicitement.

API ajoutées, admin seulement : `GET /api/v1/workers` (métadonnées publiques,
aucune clé/empreinte de credential/chemin hôte) et
`POST /api/v1/workers/{id}/revoke` avec `operation_id`. L'interface affiche le
statut révoqué et ne présente plus une identité révoquée comme prête.

Enrôlement/rotation : **CLI locale hors ligne**, même verrou que le backend,
autorité du propriétaire du répertoire. L'ancien fichier n'est ni écrasé ni
réutilisé ; un nouveau fichier d'epoch est créé sous `secrets/workers/`. Les noms
de fichiers sont publics, les valeurs ne sont jamais imprimées. Une identité
révoquée exige `--reactivate` et une nouvelle clé pour revenir active. Une
interruption de maintenance peut laisser une clé non référencée : refus fermé,
examen manuel du fichier, aucune confiance ni suppression automatique.

Seule capacité autorisée : `demo.report.v1`. Limites appliquées : une tâche active,
deadline au plus celle du backend et sortie au plus 64 Kio/configuration locale.
Capacité shell/GPU, RAM/CPU prétendument limités et champs inconnus refusés.
`isolation.enforced=false` : aucune isolation OS promise. Voir l'étude indépendante
[WORKER_ISOLATION_B52.md](WORKER_ISOLATION_B52.md).

TESTÉ : 116 tests cumulés (+15), couvrant refus d'anciennes clés/principaux,
révocation en cours, cache d'opération, accès entre deux workers enrôlés, rotation
CLI refusée sur backend actif, politique de sortie/deadline, migration B5.1 et
registre restauré révoqué après redémarrage. Les 341 tests initiaux sont conservés.

## B5.2d — validation finale et utilisation

TESTÉ : **123 tests Control Plane + 272 tests Discovery Cache = 395 tests Python**.
Les 341 tests d'origine et le scénario Firefox B5.1 sont conservés sans modification.
Le scénario navigateur couvre brouillon/approbation, HTML inerte, worker séparé,
download réel, versions autorisées, deux uploads, backend et worker redémarrés,
même SHA256, largeur mobile et verrouillage. Runtime réel : Python 3.12.3,
SQLite 3.45.1, Firefox 158.0.1 / geckodriver 0.37.1, rendu logiciel. Aucun GPU.

Revue finale : validation des réponses métier worker (enveloppes, IDs, capacité,
état, deadline et acquittement correspondant à la mission). Une chaîne d'état
inattendue n'est ni retournée au CLI ni affichée comme un diagnostic de confiance.
Quatre tests négatifs supplémentaires et un test des CLI backup/restore/réenrôlement
ont été ajoutés au lot final. `git diff --check` et syntaxe JavaScript vérifiés.

Un test de compatibilité supplémentaire couvre les sauvegardes antérieures au
registre : leurs migrations sont appliquées dans la destination, puis toutes
les identités révoquées **avant** le marqueur d'acceptation. Le worker legacy ne
peut pas être activé par une migration différée au premier démarrage. Le code
de migration est partagé avec Store ; aucun test historique n'a été ajusté.

Prérequis SQLite relevé à **3.31.0** pour disposer de `trusted_schema=OFF`
([introduction officielle](https://www.sqlite.org/releaselog/3_31_0.html)) : refus
avant création de données si le runtime est plus ancien, cas testé. Aucune
installation/mise à niveau automatique ; le runtime testé est déjà en 3.45.1.

Les références B3.3 restent inchangées. Aucun fichier historique du Discovery
Cache, test B5.1, document B5.0 ou fichier d'infrastructure modifié. La migration
SQLite concerne **uniquement l'index applicatif du Control Plane**. Aucun POC ou
catalogue personnel touché.

La [procédure Debian 13 / Python 3.13](B52_DEBIAN13_VALIDATION.md) est préparée :
**non exécutée**, aucune action sur la VM existante. Elle utilise un checkout et
des données temporaires indépendants, sans installation automatique.

### Sauvegarder et restaurer

Arrêter backend et worker, choisir des destinations **inexistantes**, privées,
hors du code et hors de la source. Exemple dans un répertoire de test contrôlé :

```bash
python3 -m control_plane backup --data-dir "$PEPEUCH_B52_CHECK_DIR/source" --destination "$PEPEUCH_B52_CHECK_DIR/backup"
python3 -m control_plane restore --backup-dir "$PEPEUCH_B52_CHECK_DIR/backup" --data-dir "$PEPEUCH_B52_CHECK_DIR/restored"
```

La sauvegarde peut être copiée hors machine via un canal/stockage privé protégé
par l'opérateur. Aucun transport externe ni chiffrement d'archive n'est fourni.
Elle contient des données applicatives potentiellement privées, **aucun credential
de connexion réutilisable**. Une sauvegarde altérée dont l'attaquant réécrit aussi
les hashes n'est pas authentifiée cryptographiquement : la provenance du support
doit rester de confiance.

Après restauration : nouvelle clé admin, mêmes missions/fichiers et identités
worker conservées mais révoquées, epochs augmentés. L'ancien `worker.token` de
la source est refusé ; celui nouvellement généré n'active pas les workers restaurés.
Ne pas démarrer deux copies comme s'il s'agissait d'un cluster distribué : aucun
protocole de consensus ou d'appairage interserveurs n'est implémenté.

### Enrôler, révoquer et renouveler

Backend arrêté, l'enrôlement crée un ID opaque et imprime **uniquement** un
descripteur public et le nom relatif du nouveau fichier privé :

```bash
python3 -m control_plane worker-enroll --data-dir "$PEPEUCH_B52_CHECK_DIR/restored" --capability demo.report.v1 --lease-seconds 30 --max-output-bytes 32768
python3 -m control_plane worker-rotate --data-dir "$PEPEUCH_B52_CHECK_DIR/restored" --worker-id fake-cpu --reactivate
```

`--reactivate` est obligatoire si l'identité est révoquée. Sans ce flag, une simple
rotation ne la réactive pas. L'enrôlement ne transfère aucune permission OS ; seul
le propriétaire local du répertoire réalise cette maintenance.

Après redémarrage du backend, lancer le worker avec **le fichier retourné** par
la commande précédente (chemin absolu sous `secrets/`) :

```bash
python3 -m control_plane worker --data-dir "$PEPEUCH_B52_CHECK_DIR/restored" --credential-file "$PEPEUCH_B52_CHECK_DIR/restored/secrets/workers/fake-cpu.3.token" --once
```

L'epoch `.3` est un exemple ; reprendre le nom effectivement retourné, sans le
deviner. Aucun contenu de credential n'est passé dans la ligne de commande.
Le fichier legacy `secrets/worker.token` reste valable pour une installation
B5.1 migrée non révoquée/non renouvelée ; il n'est jamais accepté comme repli
après une rotation. Il n'est pas supprimé automatiquement.

La révocation en ligne utilise l'API admin `POST /api/v1/workers/{id}/revoke`
et un UUID `operation_id`. Elle est idempotente ; aucune API d'émission de secret
n'est exposée. Une requête déjà authentifiée est contrôlée de nouveau en transaction.
Les tâches en file sur cette identité ne sont pas réaffectées automatiquement.

### Relancer les contrôles

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/control_plane -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s database/poc -p 'test_*.py' -q
node --check control_plane/web/app.js  # facultatif, Node déjà présent
git diff --check
```

Les tests HTTP nécessitent des sockets loopback ; les deadlines sont testées par
horloge injectée, avec un test de timeout HTTP synchronisé par socket, sans sleep
artificiel. Tests de résilience dans des temporaires privés, pas sous `/opt`.

### Limites restantes et suites

- `http.server` et ce sous-ensemble strict ne sont pas une validation production.
  HTTP/1 local seulement, sans TLS/LAN, cookies, proxy, auto-découverte ou débit garanti.
- Processus sous le même UID ; fichiers backend et clés restent accessibles au
  propriétaire local. Isolation OS/cgroups/conteneur étudiée mais **non appliquée**.
- Révocation bloquant le contrôle du cluster, pas arrêt forcé d'un processus hostile.
  CPU/RAM/PID physiques non limités ; aucune exécution arbitraire autorisée.
- Credentials admin lus au démarrage, pas de comptes multiples, PKI ou rotation admin
  en ligne. Registre local de workers simulés, pas enrôlement LAN/mTLS.
- Rétention sans purge ; copies interrompues et clés non référencées à examiner
  manuellement. Aucun garbage collector, sauvegarde à chaud ou chiffrement embarqué.
- Avant un worker réel : profil OS vérifié négativement, baux/réseau/outils
  autorisés, processus enfants et politique de récupération définis ; nouvelle
  autorisation requise avant installation ou essai matériel.

### Inventaire du lot

Créés : `control_plane/http_io.py`, `backup.py`, `worker_registry.py`,
`control_plane/migrations/0002.sql` ; tests `test_http_b52.py`, `test_backup_b52.py`,
`test_workers_b52.py` sous `tests/control_plane/` ; ce journal,
`WORKER_ISOLATION_B52.md` et `B52_DEBIAN13_VALIDATION.md`.
Actualisés : authentification, CLI, contrats internes, service/exécution,
workspace, adaptateur HTTP/client worker, panneau worker WebUI, README et TODO.
