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
