# B5.3.1 — audit, vérification stricte et pilote non exécuté

Base propre vérifiée sur `feat/webui-control-plane-b53` : `7dfb505`, `7ae7a01`,
`572e4c4`. Aucun changement de `main`, push, installation, compte, règle réseau,
service ou VM. Le présent lot conserve le refus strict par défaut.

## Lot 1 — reproductions avant corrections

Les six nouveaux tests de `tests/isolation/test_audit_fixes.py` échouaient sur
B5.3 (4 échecs, 2 erreurs), puis passent après correction. Données synthétiques dans
des répertoires privés de test ; aucune ouverture d'un vrai secret.

| Risque | Gravité et précondition | Preuve | État |
|---|---|---|---|
| Substitution d'un parent entre validation et ouverture | Élevée si un acteur peut renommer un parent ; pas une évasion de sandbox démontrée | Tests de course lecture/création : B5.3 accédait au répertoire substitué | Corrigé par parcours `openat`/`dir_fd`, `O_DIRECTORY`/`O_NOFOLLOW` sur chaque composant et opérations ancrées |
| Suppression d'un fichier préexistant sur collision du journal temporaire | Moyenne ; collision naturelle très improbable, reproductible avec nom imposé | Test `temporary_collision` : fichier préexistant supprimé avant correction | Corrigé : nettoyage du seul inode effectivement créé par cette opération |
| Fichier de verrou validé puis rouvert | Moyenne ; substitution locale/concurrence au même UID | Deux ouvertures distinctes observées par le test `lock_is_validated` | Corrigé : `fstat` et `flock` sur le même descripteur non bloquant |
| Configuration du runner conservée par référence | Faible à moyenne ; mutation dans le processus appelant | Modification externe de l'ID et des limites après construction | Corrigé : validation et copie défensive à l'entrée |
| Booléens d'affichage acceptés comme preuve par `require_verified` | Élevée pour une intégration future ; CLI B5.3 complète restait bloquée | Une propriété inventée `SecurityProperty(...True,True)` suffisait au helper | Corrigé : helper déclaratif incapable d'autoriser un lancement |
| Initialisation suivant des parents par chemin après contrôle | Même famille que la course parent | La primitive d'initialisation utilise désormais le même parcours ancré | Corrigé par création relative au descripteur parent ; tests complémentaires du vérificateur |

Ces corrections ne protègent pas contre un acteur possédant déjà tous les droits
du compte worker sur son propre état. Elles empêchent les redirections par chemin
et les erreurs de nettoyage observées ; l'isolation OS reste une frontière distincte.

## Constats inchangés à traiter dans les lots suivants

- L'observation d'un UID égal à une valeur fournie ne prouve pas l'identité du
  backend, l'exclusivité du compte, la fermeture réseau ou les montages.
- Les credentials sont opaques : la livraison opérateur doit être limitée au
  credential worker enrôlé. Aucun chemin de données backend n'est nécessaire au
  worker ; les refus API ne prouvent pas un refus d'accès physique à SQLite.
- Le filtre IP systemd ne limite pas les ports. Le gabarit nftables est par UID,
  donc affecterait tout compte partagé ; compte exclusif et revue des règles
  existantes indispensables. Aucune règle chargée pendant cet audit.
- CPU/RAM/PID/runtime et arrêt des enfants restent `NOT VERIFIED` en OS. Les
  deadlines applicatives et les epochs/générations serveur sont déjà testées.
- Tout rapport stocké ou envoyé par le worker est une donnée non fiable tant qu'une
  autorité distincte ne l'a pas recueilli, lié à l'exécution et authentifié.

## Lot 2 — diagnostic Linux et intégration stricte

Le [contrat de vérification](ISOLATION_VERIFICATION_B531.md) décrit les schémas,
bindings, contrôles et limites. Lectures bornées, cgroup v2 sans repli, PID/starttime/
boot/namespaces/inode, groupes et privilèges, limites réellement lisibles et
montages sont séparés des exigences. Les métadonnées d'unité sont obtenues seulement
par un `systemctl show` fixe du contrôleur, pas par un shell worker.

Le canal optionnel hérité vérifie le créateur et **l'auteur de chaque message**,
les nonces, le contexte, les empreintes, la couverture des garanties et la lease.
Les preuves sont recontrôlées avant attribution, calcul et publication/reprise.
Un refus tardif préserve le résultat local durable sans le publier. Aucun module
du worker n'importe une base ou lance un subprocess ; la commande fixe d'observation
systemd appartient au vérificateur séparé, chargé seulement par l'opérateur.

| Risque complémentaire | État précis et preuve |
|---|---|
| Prendre les credentials de création d'un socket hérité pour ceux de l'auteur actuel | Conception protégée par `SCM_CREDENTIALS` ; tests de message non root, credentials absents/changés/tronqués et IPC réelle non privilégiée. Aucun test de contrôleur root exécuté. |
| Rejeu d'un reçu après redémarrage/changement de configuration/profil/cgroup | Validation de portée/fraîcheur testée ; un reçu valide structurellement ne devient jamais une autorité. |
| Perte/changement de preuve après calcul | Guards testés avant claim/calcul/finish et reprise ; journal préservé, aucun finish envoyé après refus. |
| Credentials/fds inattendus dans le framing | Framing sous taille/deadline et fermeture des FD inattendus testés. |
| Options de montage pouvant contenir des données sensibles | Rapport limité aux flags connus, sans source de montage ni options libres ; test de suppression de valeur synthétique sensible. |
| `ProcSubset=pid` masque le boot ID requis | Gabarit proposé corrigé en `all`, protections de tunables conservées ; effet OS encore NOT VERIFIED. |
| Fichier root ou JSON « verified » pris pour une attestation | Aucune telle entrée d'autorisation ; diagnostic toujours NOT VERIFIED. Contrôleur livré limité au refus. |
| Socket IPv4 hérité créé par un autre UID contournant un filtre `skuid` | Risque résiduel élevé si FD non maîtrisés : inventaire de FD et garantie indépendante obligatoires, pas de validation annoncée. |

La validation du permis positif est testée seulement avec des fixtures de protocole.
Le contrôleur livré n'en émet pas : l'autorité indépendante, la qualification OS et
la promotion d'une preuve côté serveur restent hors activation dans cette mission.

## Lots 3/4 — banc séparé et préparation du pilote

Le [banc opérateur](../../pilot/worker_isolation/README.md) est dans `pilot/`, pas
dans le worker ou un scheduler. Les modules importés par unittest n'exécutent aucune
sonde. Le préparateur et le contrôleur exigent une action de pilote explicite et
root ; ils n'ont pas été exécutés. Les sondes opèrent seulement sur une racine
synthétique liée à un run ID, des endpoints privés approuvés et des cas fixes.

Ouverture sans lecture/écriture si un refus échoue ; ENOENT/ECONNREFUSED/timeout
inconclusifs ; pas de vrai secret, connexion Docker, ouverture GPU, Internet, charge
globale ou fork bomb. Cas de cycle de vie refusés sans plafonds cgroup observés,
un enfant au plus, délais fixes et témoin externe nécessaire. Résultat de sonde
toujours non vérifié, jamais converti automatiquement en reçu authentifié.

## Matrice résiduelle avant un permis réel

| Risque | Gravité / condition | État et décision nécessaire |
|---|---|---|
| Autorité qui reprend simplement une sortie worker | Élevée : preuve falsifiable | Producteur qualifié absent ; le contrôleur livré refuse toujours. Qualifier une collecte indépendante avant toute émission positive. |
| UID partagé, groupes/ACL et autres processus du même compte | Élevée : droits échappant au seul cgroup | Compte exclusif, inventaire et permissions hôte à confirmer sur la VM jetable. Aucun compte créé ici. |
| Code RO dans le namespace mais modifiable via l'hôte/un autre processus | Élevée si code/ancêtres inscriptibles | Garantie indépendante `code_integrity` obligatoire et inconnue ; propriétaire/admin, contenu et release à mesurer. |
| Restriction nftables par UID, IPv6 et connexions héritées | Élevée si UID partagé, FD d'un autre créateur ou règle inopérante | Aucun chargement ; inventaire FD, pairs contrôlés, compteurs et interaction avec l'existant à qualifier. |
| Test de durée/arrêt qui tue son propre témoin | Élevée pour une fausse preuve | Superviseur externe, PID/starttime et cgroup recontrôlés, qualification du profil distincte du lancement courant. |
| Écart entre contrôle et utilisation / fin d'une lease | Moyen à élevé pour un futur permis | Rechecks rapprochés implémentés ; pas de preuve d'enforcement continu ni attestation de commit serveur. Synchronisation/supervision à concevoir avant production. |
| GPU/Docker absents ou errno ambigu | Moyen : faux positif de test | Métadonnées seulement ; absence comparée à l'hôte et politique réelle requises. Aucune ouverture GPU/connexion Docker ici. |
| Canari hôte 0666 et helpers root temporaires | Moyen, limité au nouveau pilote | Changements exacts à autoriser explicitement, canari non sensible, chemins neufs, pas de nettoyage global ni d'activation permanente. |
| Restauration d'une ancienne preuve | Élevée si acceptée implicitement | Recevabilité liée au boot/PID/starttime/configuration/politique ; pas de réactivation via une sauvegarde ou un fichier « approved ». |

## Validation finale et garanties

- **506 tests Python réussis** : 123 Control Plane, 272 Discovery Cache, 48 worker
  B5.3 inchangés et 63 nouveaux tests B5.3.1. Les scénarios d'échec précèdent les
  fixtures de succès ; six reproductions ont échoué sur B5.3 avant correction.
- Firefox 158.0.1/geckodriver existant : parcours historique réussi (approbation,
  versions, XSS, worker séparé, téléchargement/SHA, redémarrage, mobile, logout).
- Les tests nouveaux sont unitaires/synthétiques, avec un diagnostic réel en lecture
  seule et une paire IPC réelle privée **non privilégiée**. `SO_PASSCRED` requiert un
  runner autorisant cette option ; le sandbox Codex la bloque, le test a passé sous
  l'UID courant hors sandbox, sans sudo/root, listener ou configuration réseau.
- Aucun test négatif OS sous systemd, préparateur de canaris root, contrôleur root,
  charge cgroup ou règle nftables exécuté. **Isolation OS : NOT VERIFIED**.
- Fichiers des 443 tests antérieurs, Control Plane, Discovery Cache, migrations et
  bases POC préservés ; aucune collecte, inférence ou modification de `main`.
- `git diff --check` propre ; unité et drop-in FD rendus acceptés par
  `systemd-analyze verify --man=no --generators=no` local, sans chargement/activation.
  Analyse de motifs de secrets : aucun signalement, complétée par la revue manuelle.
  Les validations ordinaires ont tourné sous UID 1000 ; les opérations root du banc
  restent simulées ou non exécutées. Référence B3.3 conservée :
  `ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.

La validation de structure, la vérification d'un auteur root et les mesures noyau
sont trois opérations différentes. Le statut global positif reste bloqué faute
d'une chaîne qualifiée d'épreuves indépendantes. Les interfaces du contrôleur
permettent de tester les refus ; elles ne sont pas un service de production.

## Fichiers concernés

- Corrections : `pepeuch_worker/private_io.py`, `contracts.py`, `runner.py`,
  `__main__.py`, `isolation.py`.
- Nouveau vérificateur : `linux_observer.py`, `verification.py`,
  `verification_channel.py`, `verifier.py` dans le même package.
- Nouveau banc : `pilot/__init__.py`, `pilot/worker_isolation/` (modules et guide).
- Tests : `tests/isolation/` (fixtures, audit, Linux, canaux, guards, sondes et CLI).
- Gabarits : unité B5.3 ajustée, drop-in FD et exemples publics de politique/scope
  dans `deploy/worker-linux/`. Aucun de ces fichiers n'a été installé.
- Documentation : ce rapport, le contrat de vérification, le contrat B5.3, le guide
  Debian, le journal B5.3 et `TODO.md`.

Prochain lot recommandé : **B5.3.2, pilote négatif supervisé sur VM jetable**, après
revue et confirmations du plan Debian. D'abord corroborer les preuves et terminer
le producteur indépendant ; aucune émission positive, exposition LAN ou inférence
tant que les garanties obligatoires restent inconnues.
