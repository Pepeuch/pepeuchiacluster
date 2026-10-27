# Contrat B5.3 — worker CPU indépendant

## Identités et frontières

| Élément | Contrat effectif | Limite de la preuve |
|---|---|---|
| Cluster | `n_<32 hex>`, enrôlement B5.2, capacité unique `cpu.text.sha256.v1` | Aucun rapprochement avec un nom de machine, compte ou fournisseur |
| Authentification | Bearer worker uniquement, empreinte serveur, epoch validée à chaque requête/transaction | Une clé authentifie une identité ; elle ne prouve pas l'isolation |
| Processus | UID/GID attendus dans `os_profile`, observations UID/GID/groupes dans `inspect` | Exclusivité du compte et identité réelle du backend à vérifier séparément |
| Persistance serveur | SQLite, objets, secrets admin et workspaces restent exclusivement côté serveur | Le refus d'accès physique dépend de l'OS, pas des routes HTTP |
| Persistance worker | Répertoire propre 0700, configuration/journal 0600, credential 0600/0400 | En mode de test, le même UID peut encore lire d'autres fichiers de son compte |
| Transport | HTTP direct `127.0.0.1:port`, aucun DNS/proxy/redirection ; 5 s par échange | Application loopback, sans TLS ni appairage LAN ; aucun serveur distant accepté |
| Routes worker | Claim, état d'une tentative, finish ; identité/epoch/tentative contrôlées | Aucun téléchargement d'entrée ni accès aux routes administrateur |

Schémas : `pepeuch.worker/config/v1`, `security-evidence/v1`, `run/v1` et
`cpu-text-digest/v1`. Les trois derniers partagent le préfixe `pepeuch.worker/`.
La configuration est fermée et copiée défensivement : inconnus, outils, capacités
non prévues, limites booléennes ou hors bornes sont refusés. Le fichier d'exemple
ne contient que des identités factices et des paramètres publics : remplacer
l'ID nul et les UID/GID indicatifs, ne jamais réutiliser le compte `nobody`.

## Autorisation et exécution

1. L'administrateur crée un brouillon par `/api/v1/cpu-missions` avec
   `operation_id`, `title`, `objective`, `workspace_id` et éventuellement
   `authorized_files: []`. Tout fichier non vide ou champ outil/chemin est refusé.
2. Une intention typée unique est ajoutée au journal d'audit dans la même
   transaction. Ce n'est pas une instruction issue du texte utilisateur.
3. L'approbation explicite applique un routage fixe, rôle `cpu-text-digest`,
   instruction `hash_authorized_objective_utf8`, sortie unique `resultat.md`.
   Premier worker actif compatible dans l'ordre du registre ; pas de scheduler,
   de sélection matérielle ou d'équilibrage. Aucun LLM coordinateur.
4. Attribution B5.2 : tâche, tentative, génération, epoch, deadline et version
   attendue du livrable. Le worker valide aussi son propre ID et la capacité.
5. Calcul SHA256 du texte UTF-8, par blocs de 512 octets. Maximum 16 000 octets
   d'entrée, 65 536 de sortie, 30 s coopératives et une tâche. Les plafonds locaux
   peuvent être réduits ; les plafonds serveur restent indépendamment appliqués.
6. Résultat `execution-result/v1` publié par la même route B5.2. Format de fichier
   markdown contenant du JSON structuré, SHA256 et nombre d'octets. Aucun shell,
   `eval`, subprocess, outil, accès arbitraire aux fichiers ou fournisseur réseau.

Le texte peut ressembler à une commande : il reste des données hachées. Aucune
inférence IA ni analyse sémantique. Les références de versions de fichiers restent
prises en charge par la démo historique ; ce worker ne les consomme pas. Un futur
contrat de lecture devra autoriser version/workspace/tentative, borner les octets
et vérifier les empreintes avant d'élargir ce périmètre.

Les enveloppes B5.2 restent versionnées v1 ; les valeurs ajoutées sont la capacité
CPU et les erreurs `cpu_execution_failed`, `cpu_interrupted`,
`cpu_deadline_exceeded`. Elles sont contrôlées selon la capacité de la tâche.
Un client B5.2 continue de refuser une tâche CPU ; un client CPU refuse une tâche
de démo. Les anciens corps, identités, migrations, clés d'idempotence et sorties
de simulation sont inchangés. Aucun contrat Discovery/Personal Model Catalog modifié.

## Reprises, arrêt et résultats

| Situation | Comportement |
|---|---|
| Arrêt normal sans tâche | Une seule attribution ; état `idle`, pas de boucle |
| Perte de réponse au claim | Journal d'opération écrit avant HTTP ; `--recover` rejoue la même opération |
| Claim acquis, résultat absent au redémarrage | Interruption durable, aucun recalcul automatique |
| Résultat local durable, serveur encore actif | Réémission identique après contrôle de l'état |
| Serveur a déjà terminé / expiration / redémarrage | Observer l'état terminal ; ne pas publier/recalculer |
| Credential changé ou endpoint changé pendant une reprise | Refus local ; aucune réassociation implicite du journal |
| Credential révoqué/ancien epoch ou génération périmée | Refus serveur, même si le résultat a été calculé avant révocation |
| SIGINT/SIGTERM | Demande d'arrêt coopérative, points de contrôle pendant le calcul ; I/O HTTP bornée |
| Arrêt forcé / enfants / consommation RAM | Garantie OS encore `NOT VERIFIED` ; protocole de validation séparé |

Une reprise du journal ne constitue pas une nouvelle autorisation de calcul.
Après interruption, l'administrateur décide d'une nouvelle tentative B5.2 ;
conserver/archiver le journal privé de l'ancienne identité si nécessaire, sans
suppression automatique. La rotation opérationnelle est hors ligne : arrêter le
worker et le backend, renouveler, livrer le nouveau fichier, reprendre manuellement.
Le redémarrage backend fence les anciennes tentatives. Un journal actif lié à
l'ancienne clé ne peut être repris avec la nouvelle ; utiliser une nouvelle racine
worker pour la nouvelle identité/epoch après résolution de la tentative serveur.

Le serveur ne confond pas « fichier reçu avec intégrité vérifiée » et « calcul
attesté dans une sandbox ». Les résultats CPU sont marqués non simulés, sans IA,
`worker_reported_cpu_digest`, isolation `NOT VERIFIED`. L'audit ne contient que
des IDs, capacités et codes constants. Le journal worker privé peut contenir le
texte approuvé ; il ne fait pas partie des logs ni de la sauvegarde backend.
Les sauvegardes B5.2 conservent intention, événements, versions et résultats CPU ;
la restauration renouvelle les clés et maintient tous les workers révoqués.

## Déclarations et preuves OS

Chaque propriété expose `declared`, `enforced` (`true`, `false` ou inconnu `null`),
`verified` et `evidence`. Les observations `/proc/self/status`, groupes et cgroup
sont de simples observations datées par l'exécution ; aucun booléen JSON fourni
par un worker ne peut déverrouiller le lancement strict. Même l'observation d'un
UID distinct ne prouve pas une sandbox complète.

**Le mode strict refuse actuellement tout lancement CPU**, avant lecture du
credential par l'application et avant connexion, parce que l'ensemble des preuves
obligatoires n'est pas disponible. L'inspecteur n'est pas encore un vérificateur
complet de mounts, cgroup/eBPF, droits et arrêt de groupe. Le gabarit systemd ne
change pas cet état. Seul `run --application-test` permet de tester le parcours
fonctionnel, avec l'indication explicite `NOT VERIFIED` ; il ne crée aucune preuve
OS et n'est pas un mode de déploiement sécurisé.

## Suites possibles

- Valider les propriétés OS sur une machine Debian 13 jetable autorisée, puis
  concevoir un vérificateur de confiance lié au processus/cgroup et à sa durée de
  vie. Ne pas accepter une attestation JSON arbitraire ou un fichier « approved ».
- Fermer le réseau au port backend au niveau OS : le filtre IP du gabarit laisse
  tous les ports de `127.0.0.1` accessibles si l'eBPF fonctionne. Le client applicatif
  fixe un seul port, ce qui constitue une protection distincte. Un gabarit nftables
  par UID/port est proposé séparément, sans chargement ni validation noyau ; son
  expérimentation exige une autorisation spécifique et un compte exclusif.
- Définir les preuves de ressources, de terminaison et les budgets cumulés I/O +
  calcul avant une charge plus lourde. Ajouter les fichiers d'entrée par un contrat
  API distinct, sans donner de chemin backend au worker.
- Linux autonome seulement pour ce lot (`fcntl`, UID/GID, `/proc`). Windows devra
  définir jeton restreint, ACL, Job Objects et règles réseau ; macOS un contrat de
  sandbox/ressources équivalent. Leur état reste non pris en charge et non vérifié.
  Les futurs runtimes pourront changer l'exécuteur typé, pas contourner les
  générations, permissions et publications. Open WebUI/AnythingLLM restent des
  interfaces facultatives, sans dépendance dans ce package worker.
