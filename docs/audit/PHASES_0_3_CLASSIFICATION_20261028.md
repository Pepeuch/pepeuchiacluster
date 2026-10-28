# Reprise phases 0 à 3 — classification des 35 cases

28 octobre 2026. Branche `feat/phases-0-3-integrity-cas`, base
`5ead5754bd3424356eaf243bf6db271337a8faaa`. La TODO publiée sur main est
préservée comme baseline ; aucun commit, merge, rebase ou push de cette reprise.
Les six commits `21dba8f` → `453fb08` sont ancêtres de main et la référence
publiée `origin/feat/todo-phases-0-3` a été vérifiée par `git ls-remote`.
`main` a deux commits supplémentaires : intégration et mise à jour de la TODO.

Une classification principale par ligne composite ; ses sous-tâches peuvent
appartenir à d’autres catégories. IMPLEMENTABLE n’implique pas que toute la ligne
soit clôturable sans décision ou validation réelle. TESTABLE n’autorise aucun
changement système. G1 = Proxmox/VM ; G3 = pilote OS distinct. Les tâches des
nouvelles sections 9.1/10.1/13.1/17.1/17.2 et de 3.1+ restent futures.

Répartition initiale : BLOCKED = 15, DECISION REQUIRED = 11, IMPLEMENTABLE = 5, TESTABLE = 4.

| ID stable | Ligne TODO à la base | Case initiale | Classe principale | Dépendance / limite |
|---|---:|---|---|---|
| T01 | 115 | Créer la VM via le script Proxmox | **BLOCKED** | G1 : accès Proxmox et VM jetable autorisés absents ; script seulement simulé. |
| T02 | 126 | Définir sauvegarde de la VM | **BLOCKED** | G1 : stratégie préparée, sauvegarde Proxmox réelle non autorisée. |
| T03 | 138 | Définir et vérifier une sauvegarde/restauration Proxmox de la VM 150 avant d'y stocker des données irremplaçables. | **BLOCKED** | G1 : restauration VM150 vers une autre destination exige un GO spécifique. |
| T04 | 139 | Confirmer la disponibilité courante des healthchecks des deux bases après autorisation : cinq dernières sondes de chaque base réussies avant l’arrêt, mais conteneurs actuellement arrêtés ; aucun démarrage autorisé. | **BLOCKED** | GO spécifique démarrage POC absent ; ne pas intervenir sur les conteneurs historiques. |
| T05 | 182 | Étendre les sondes à plusieurs modèles et formats ; vérifier les révisions, fichiers, relations et éventuelles restrictions d'accès. L'API sondée ne fournit pas de SHA Git exploitable. | **BLOCKED** | Périmètre spécifique de source/révisions réelles différé ; arrêt avant 3.1. |
| T06 | 192 | Étendre les sondes à d'autres dépôts et étudier séparément les ressources datasets, spaces, MCP, skills et les modèles servis par l'AI Gateway. | **BLOCKED** | Extensions de sources/familles de ressources différées ; aucune collecte réelle autorisée ici. |
| T07 | 202 | Synchroniser les fichiers locaux non suivis de la VM avec la branche publiée, après comparaison ; voir [la procédure ciblée](database/poc/MOARK_VM_SYNC.md). | **BLOCKED** | Comparaison des locaux VM puis autorisation de synchronisation requises ; préserver le dépôt VM. |
| T08 | 203 | Étudier séparément capacités, quotas applicables et dépôts de poids MoArk/Gitee ; aucune association automatique par nom. | **BLOCKED** | Étude propre à MoArk/Gitee différée ; pas d’inférence ou téléchargement. |
| T09 | 215 | Décider la sémantique future des accès/visibilités, de l'isolation domaines/comptes, des révisions et des collectes partielles avant toute évolution de format ou d'identité. | **DECISION REQUIRED** | Sémantique accès/révisions et isolation de stockage à trancher sans changer les clés B2. |
| T10 | 231 | Décider et tester la politique de redirections B1 avant sa migration ; préserver le cas NIM 404 et les limites du SDK. Voir [TRANSPORT_B42.md](database/poc/TRANSPORT_B42.md). | **IMPLEMENTABLE** | Politique de redirection testable hors ligne ; migration B1 différée tant que garanties non qualifiées. |
| T11 | 239 | Examiner le prototype et décider multitag NIM, namespaces domaines/comptes, provenance synthétique/réelle et conventions de collecte partielle avant un registre opérationnel. | **DECISION REQUIRED** | NIM multitag, domaines/comptes et collecte partielle : décisions communes, pas de nouvelle identité implicite. |
| T12 | 248 | Examiner le registre manuel avant toute extension online ; provenance synthétique/réelle, domaines/comptes, NIM multitag et résultats partiels restent à décider. | **DECISION REQUIRED** | Mêmes dépendances que le registre ; aucune extension online implicite. |
| T13 | 258 | Décider la provenance obligatoire et le contrat d'import avant toute protection complète du B2 brut ; l'option ne remplace pas une validation d'origine. | **IMPLEMENTABLE** | Primitives de provenance/intégrité/CAS réalisables ; origine obligatoire et isolation restent des décisions. |
| T14 | 268 | Définir l'enrôlement/rotation/révocation des émetteurs et la CLI protégée ; HMAC local ne prouve pas une collecte distante. | **IMPLEMENTABLE** | Gestion locale émetteurs/rotation/révocation et génération contrôlée réalisables sans collecte distante. |
| T15 | 269 | Raccorder les reçus HTTP conditionnels au moteur budgété, la reprise inter-sources et les politiques de fraîcheur avant de déclarer B4.5 opérationnel. | **IMPLEMENTABLE** | Raccordement 304/budgets/fraîcheur injectable et reprise testables hors ligne ; pas de transport réel. |
| T16 | 270 | Définir pagination distante, garanties/quotas SDK, concurrence par hôte et budget global dans des lots séparés ; aucun scheduler. | **DECISION REQUIRED** | Pagination/SDK réels et politiques de quotas/concurrence à définir ; ne pas inventer les quotas. |
| T17 | 279 | Valider les contrats d'identité/appairage/bail et l'API de mission avant B5.1 ; développer un faux worker puis autoriser séparément un pilote Linux CPU. | **TESTABLE** | API/baux/faux worker déjà présents ; volet pilote OS/appairage/TLS bloqué par G3. |
| T18 | 280 | Choisir langage/packaging, stockage durable et politique de clés ; vérifier licences/artefacts exacts, notamment Desktop avant toute redistribution. | **DECISION REQUIRED** | Choix prototype connu ; packaging, clés et licences exactes de distribution restent à approuver. |
| T19 | 281 | Établir une matrice réellement testée par OS/runtime ; aucune capacité GPU/inférence/agent annoncée comme vérifiée par cette étude. | **BLOCKED** | Machines et profils OS/runtime dédiés non disponibles/qualifiés. |
| T20 | 282 | Garder interfaces tierces, VM automatisée, compagnon multi-OS et USB dans des lots séparés ; aucune installation/provisionnement/migration effectués dans B5.0. | **TESTABLE** | Revoir les études B5.0 et leur séparation ; ne pas assimiler cette règle à une livraison des quatre méthodes. |
| T21 | 294 | Finaliser la pile HTTP de production et l'isolation OS d'un vrai worker ; les contrôles locaux HTTP/identité/sauvegarde sont validés au checkpoint B5.2, sans exposition LAN. | **BLOCKED** | Pile production et pilote OS exigent environnement et autorisation dédiés. |
| T22 | 295 | Définir les contrats agents/rôles/baux réels, appairage/TLS et politiques multi-utilisateurs avant une ouverture LAN ou exécution d'outils ; aucune installation, inférence ou collecte réelle dans B5.1. | **DECISION REQUIRED** | Agents/outils/appairage/TLS multi-utilisateurs : contrats réels à choisir, sans ouverture LAN. |
| T23 | 307 | Avant un vrai worker : isolation OS éprouvée, politiques réseau/outils/enfants, PKI/appairage/TLS et pile HTTP de production ; conserver le prototype sans IA réelle ni découverte LAN. | **BLOCKED** | G3 : preuve OS, réseau/outils/enfants et PKI manquantes. |
| T24 | 317 | Autoriser puis exécuter les tests négatifs OS sur une machine distincte : UID/groupes, secrets/SQLite/objets inaccessibles, FS, réseau, GPU/Docker, CPU/RAM/PID, runtime et arrêt des enfants — **NOT VERIFIED**. | **BLOCKED** | G3 : aucune VM jetable ni GO comptes/unités/pare-feu. |
| T25 | 318 | Qualifier le producteur indépendant de permis et fermer/vérifier le réseau OS au port backend ; contrats, observations et canal de refus ajoutés en B5.3.1, sans activation. `--application-test` ne valide pas l'isolation, le filtre IP candidat seul autorise tous les ports loopback. | **BLOCKED** | G3 : collecte indépendante et contrôle réseau OS des ports non qualifiés. |
| T26 | 319 | Avant une inférence ou un outil réel : contrat de lecture des versions d'entrée, quotas cumulés I/O/calcul, politique des moteurs/outils, preuves OS et profils Windows/macOS distincts ; conserver AnythingLLM/Open WebUI facultatifs. | **DECISION REQUIRED** | Contrat entrées, budgets cumulés et moteurs/outils à préparer ; vrais profils OS restent bloqués. |
| T27 | 329 | Autoriser un pilote négatif sur une **VM jetable distincte** selon [le plan opérateur Debian](docs/architecture/B53_DEBIAN13_VALIDATION.md), avec confirmations séparées pour comptes, fichiers, unités et pare-feu. Aucun accès à la VM historique autorisé. | **BLOCKED** | G3 : pilote négatif exige une VM distincte expressément autorisée. |
| T28 | 330 | Qualifier collecte indépendante, compte exclusif, code/FD/montages, règles/IPv4/IPv6/ports et ressources/arrêt avant un producteur de permis positif. Le contrôleur livré émet toujours `deny` ; strict reste bloqué, OS **NOT VERIFIED**. | **BLOCKED** | G3 : producteur indépendant positif interdit sans qualification ; strict reste deny. |
| T29 | 331 | Définir si nécessaire une attestation serveur distincte : aucun champ worker ne promeut aujourd'hui le statut `verified`. Pas de vraie inférence, modèle, GPU ou service privilégié permanent. | **DECISION REQUIRED** | Attestation serveur séparée à décider ; un worker ne se promeut pas verified. |
| T30 | 353 | Finaliser le POC comparatif **PostgreSQL vs SurrealDB** (performances, graphe, vecteurs et contraintes d'exploitation). | **TESTABLE** | Banc synthétique réalisé ; revoir bilan/limites et contraintes d’exploitation avant clôture globale. |
| T31 | 365 | Vérifier précisément les contraintes de licence de SurrealDB avant adoption | **DECISION REQUIRED** | Périmètre d’usage/distribution et notices de l’image à confirmer avant adoption. |
| T32 | 366 | Décider du moteur principal | **DECISION REQUIRED** | Choix PostgreSQL/SurrealDB attend décision utilisateur sur la recommandation conditionnelle. |
| T33 | 367 | Documenter la décision | **DECISION REQUIRED** | ADR finale dépend du choix du moteur ; rapport actuel ne vaut pas adoption. |
| T34 | 432 | Industrialiser l'ingestion incrémentale (exécution planifiée, reprise sur erreur, rétention, surveillance) ; le POC B2 est une importation **manuelle**, pas encore un Discovery Service en production. | **IMPLEMENTABLE** | Lots intégrité/CAS/reprise réalisables ; scheduler et production restent hors lot, ligne composite ouverte. |
| T35 | 441 | Éprouver les imports partiellement échoués, les changements de révision réels et les variations de périmètre ; conserver les snapshots et définir la politique de rafraîchissement. | **TESTABLE** | Imports synthétiques déjà qualifiés ; concurrence testable, révisions fournisseur et rafraîchissement réels manquants. |

Priorité locale : intégrité des snapshots et provenance → transition/revisions
sans changement d’identités → préconditions CAS et concurrence → reprises/partiels.
Les clôtures éventuelles seront inscrites avec leurs preuves dans la matrice et
le checkpoint, sans déclarer les simulations comme preuves PostgreSQL/SurrealDB.

## Première clôture après vérification documentaire

**T20 clôturée** : la ligne impose la séparation des lots et l’absence de
provisionnement dans B5.0, pas la livraison de ces parcours. Les fichiers
`NODE_PROVISIONING_DESIGN.md` (comparaison et lots), `WEBUI_CONTROL_PLANE.md`
(lots testables) et `OPEN_WEBUI_ANYTHINGLLM_STUDY.md` (clients facultatifs/worker
indépendant) l’établissent ; le commit d’origine
`6b35b4127702d9bd58f1b1aa54ab8273f90314b9` ne contient que TODO et quatre études.
Aucune installation, capacité matérielle ou sécurité OS n’est déclarée validée.

Restent 34 lignes : BLOCKED 15, DECISION REQUIRED 11, IMPLEMENTABLE 5,
TESTABLE 3. Les sous-tâches intégrité/CAS avancent T13/T34/T35 sans les clôturer
entièrement : provenance obligatoire/CLI, partitions, révisions réelles et
service de production restent requis. Les garanties PostgreSQL/SurrealDB sont
rapportées séparément des tests Python.
