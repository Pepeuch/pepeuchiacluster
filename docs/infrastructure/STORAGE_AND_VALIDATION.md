# Stockage et validations de l’infrastructure

28 octobre 2026 — politique documentée, configuration IMPLEMENTED ; montages
VM150 VERIFIED en lecture seule, bases arrêtées. Aucun volume ni service modifié.
Voir [l’inventaire réel](VM150_READONLY_20261028.md).

## État et périmètres de sauvegarde

| Données | Configuration existante | Contrôle / restauration attendus |
|---|---|---|
| PostgreSQL 16 | Compose `pepeuch-ai-poc`, volume logique `postgres_data`, destination `/var/lib/postgresql/data` | Identifier le volume réel via les montages ; dump logique cohérent et restauration dans une base distincte |
| SurrealDB 3.3.4 | Bind `/opt/pepeuch-ai/data/surreal-poc` vers `/data`, RocksDB, UID/GID 1000 | Export logique et réimport distinct ; ne pas copier RocksDB en fonctionnement comme preuve de sauvegarde cohérente |
| Configuration | `/opt/pepeuch-ai/config`, secrets hors Git | Sauvegarde chiffrée à accès restreint ; ne pas inclure son contenu dans un rapport |
| Dépôt / manifests / snapshots | `/opt/pepeuch-ai/repo`, chemins à inventorier | Git ne sauvegarde pas les fichiers non suivis ; inventorier/comparer avant stash ou pull |
| VM150 complète | Disques, configuration Proxmox et sauvegardes externes à inventorier | Sauvegarde Proxmox puis restauration sur un **nouveau VMID**, réseau isolé et GPU non attaché, après GO |
| Poids / cache | Chemins à inventorier, pas présumés inclus dans les volumes DB | Classer reproductible/irremplaçable ; évaluer capacité et durée avant politique définitive |

Conserver les projets Compose, noms de volumes, bind mounts et UID existants.
Interdire `down -v`, prune, renommage/migration, chown récursif ou écrasement d’un
export existant dans cette mission. Aucun changement des schémas historiques.
Vérifier capacité libre et croissance à partir de mesures ; aucun seuil réel
ou calendrier de rétention n’est encore adopté. Proposition à valider : exports
quotidiens, sauvegarde VM hebdomadaire, copie sur stockage distinct, rétention
dimensionnée après inventaire et restauration périodique. Un snapshot sur le
même stockage ne constitue pas à lui seul une sauvegarde indépendante.

## Lecture seule disponible

`python3 infrastructure/server/inspect_poc_health.py` n’exécute que `docker ps`
et `docker inspect --format` sur les deux labels de projet/service attendus.
Pas de sudo, exec, probe SQL, accès aux secrets, logs ou sorties de healthcheck.
Son code retour vaut 1 si un service n’est pas confirmé running/healthy avec le
montage persistant attendu. `VERIFIED` dans ce rapport signifie exclusivement
**métadonnées Docker vérifiées**, jamais intégrité des données ou persistance.
Les erreurs sont normalisées sans stderr brut. Exécution locale : deux projets
absents, donc NOT VERIFIED ; les builders existants sont préservés.

Les Compose configurent déjà `pg_isready` et `/surreal is-ready`. La configuration
ne prouve ni `healthy` actuellement, ni authentification aux données. SurrealDB
Healthy a une preuve historique utilisateur ; actuellement les deux conteneurs
sont arrêtés, health mémorisé `unhealthy`. Ils ont été préservés dans cet état.
Les cinq dernières exécutions conservées de chaque sonde ont code 0 avant l’arrêt :
readiness historique confirmée par lecture, sans redémarrage.

## Plan opérateur soumis au GO

1. VM150 inventoriée avec l’accès fourni explicitement ensuite. Tout accès
   supplémentaire Proxmox est désormais interdit ; une intervention opérateur
   et un nouveau GO seraient requis. Ne pas chercher d’autres credentials.
   Inventaire hyperviseur/configuration, stockages/capacité, tâches de backup et
   PCI en lecture seule. Pas de commandes via QEMU guest agent.
2. Définir un VMID inutilisé distinct de 150, stockage et bridge isolé, capacité,
   empreinte d’image et droits. Examiner `create-ai-vm.sh --plan` avant GO.
   Le mode sans option crée réellement une VM ; les tests locaux utilisent des
   stubs et ne qualifient pas Proxmox/cloud-init/réseau.
3. Autoriser séparément sauvegarde puis restauration vers ce nouvel ID. Ne jamais
   restaurer sur 150. Tester données et démarrage sans GPU ni réseau de production.
4. Pour la persistance DB, mesurer les mêmes identifiants/comptages/empreintes
   avant/après un redémarrage de **services de test autorisés**. Aucun redémarrage
   de VM150 ou des POC historiques n’est autorisé par ce document.
5. Mesurer CPU/RAM/disque sous charge bornée approuvée ; calcul CUDA Docker,
   inférence et stabilité prolongée demeurent NOT VERIFIED.

Retour arrière à approuver avec chaque opération : conserver VM150 et ses volumes,
identifier exactement les nouveaux objets et fichiers créés ; examiner les restes
si échec. Aucune destruction automatique ni nettoyage générique. Suppression
d’une VM test, d’un volume ou d’une sauvegarde exige un GO ciblé. Le pilote négatif
OS B5.3.1 nécessite un autre périmètre jetable et sa propre autorisation.

## GO ciblé proposé : santé des deux POC arrêtés

Non exécuté ; l’utilisateur a demandé de les conserver arrêtés après présentation
de ce plan. Ce n’est pas une autorisation en attente déduite implicitement. Un
futur GO distinct devrait couvrir exclusivement ces deux conteneurs existants :
`pepeuch-ai-poc-postgres-1` et `pepeuch-ai-surreal-poc-surrealdb-1`.

- Relever à nouveau état et montage ; refuser si identité/configuration diffère.
- Utiliser `docker start` sur ces deux objets, **sans Compose up**, pull, recreate,
  changement de configuration, schéma, import ou migration.
- Attendre au plus 120 s au total par lectures espacées d’état/health ; pas de
  charge ou benchmark. Éviter les sorties brutes de healthcheck et les secrets.
- Relever disponibilité, version, montages ; ne pas modifier les données applicatives.
- Retour arrière inclus dans le GO : `docker stop` uniquement les conteneurs que
  ce contrôle a démarrés, pour revenir à l’état initial arrêté. Si l’opérateur
  souhaite les conserver actifs, le préciser avant le GO. Ne pas toucher au daemon.

Un démarrage de base peut écrire normalement dans son stockage (recovery,
journaux) : ce n’est donc plus une opération strictement en lecture seule. Il
nécessite le GO explicite imposé par l’utilisateur. Les SELECT, essais d’import,
restaurations ou interruptions restent des validations distinctes, à cadrer
séparément. Aucun GO implicite n’est déduit du mot de passe fourni.

## Autorisation ultérieure : deux nouveaux conteneurs d’essai

Le [banc autorisé et exécuté](../../database/poc/ISOLATED_DOCKER_BENCH.md) utilise
ses propres répertoires sous `/var/tmp`, un nouveau réseau interne et les images
exactes déjà locales. Aucun POC historique démarré. Les nouveaux conteneurs sont
arrêtés, leurs données, nouveaux volumes et exports conservés jusqu’à revue.
Huit restaurations ont visé exclusivement de nouvelles bases du banc ; cela ne
valide pas une restauration Proxmox de VM150 ou les exports historiques.
