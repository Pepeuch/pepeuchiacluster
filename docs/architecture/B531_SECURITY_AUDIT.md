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
