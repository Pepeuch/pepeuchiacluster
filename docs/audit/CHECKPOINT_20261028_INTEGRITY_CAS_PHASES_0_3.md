# Checkpoint durable — intégrité/CAS des phases 0 à 3

2026-10-28T23:06:13+01:00.
Branche `feat/phases-0-3-integrity-cas`, HEAD `5ead5754bd3424356eaf243bf6db271337a8faaa`. main et origin/main vérifiés à cette base.
Aucun commit, staging, push, merge ou rebase. Le travail reste local non committé.
Aucun développement de 3.1+ ou des nouvelles sections futures de la TODO.

## Inventaire de départ et préservation

- Départ : main propre à `5ead5754bd3424356eaf243bf6db271337a8faaa`, après intégration
  de `feat/todo-phases-0-3` et publication de la TODO enrichie.
- Six commits `21dba8f`, `70b5c1b`, `a1a1d1c`, `c1df2a3`, `3124706`, `453fb08`
  vérifiés ancêtres de main et de la branche distante ; `git ls-remote` confirme
  `origin/feat/todo-phases-0-3` à `453fb08c1296e2bbbf08b68a2ef9fd9229c18eb5`.
  main a deux commits supplémentaires, sans divergence à intégrer.
- Branche nouvelle créée depuis main pour conserver la dernière TODO ; aucune
  fusion/rebase nécessaire. Le SHA de main n’a pas bougé pendant cette reprise.
- [Checkpoint initial lu](CHECKPOINT_20261028_REPRISE_PHASES_0_3.md), couverture relue.
  [Checkpoint d’inventaire de ce lot](CHECKPOINT_20261028_INVENTORY_PHASES_0_3.md).
- SHA de la TODO initiale : `a361d4f6df798aeb44e1989fd9d816ce1cf70a012410ae79024431f43dbcfb60`.
  Suffixe entier depuis `## 3.1 models.dev` inchangé, y compris 9.1/10.1/13.1/17.1/17.2.
  SHA du suffixe courant : `52f8b97ef7daa428d3dd1833c625683432ae841a5e73076ba727882d3b4ff66d`.
- Toutes les fixtures historiques et les **116 fichiers privés préexistants**
  ont gardé leur SHA256 ; aucun résultat, snapshot, dump, volume ou ancien stash
  supprimé. Nouveaux résultats privés CAS : 19 fichiers supplémentaires ignorés.

## Classement et clôture exacte

[Classification des 35 lignes initiales](PHASES_0_3_CLASSIFICATION_20261028.md),
avec ID T01–T35, classe et dépendances : 5 IMPLEMENTABLE, 4 TESTABLE,
11 DECISION REQUIRED, 15 BLOCKED à l’entrée. Une ligne composite n’est pas une
promesse de clôture avec ses seules sous-tâches logicielles.

**T20 clôturée**, après revue des études et du commit documentaire d’origine
`6b35b4127702d9bd58f1b1aa54ab8273f90314b9` : séparer interfaces, VM, compagnon
et USB est une règle d’architecture satisfaite, pas une livraison de ces quatre
méthodes. Le commit ne contient que TODO et quatre études, et les plans séparent
les futurs provisionneurs. Aucune nouvelle qualification matérielle/OS.

**34 lignes initiales restent ouvertes** : phase 1 = 28, phase 2 = 4,
phase 3 générale = 2. Classement restant : IMPLEMENTABLE 5, TESTABLE 3,
DECISION REQUIRED 11, BLOCKED 15. Deux nouvelles sous-tâches intégrité/CAS
sont cochées avec leurs preuves, sans fermer artificiellement les composites.

## Corrections réalisées et contrat livré

1. Validation B2 exige enveloppe exacte et date explicite non nulle. Le lecteur
   n’invente plus une date courante ; erreur avant SQL, pas de KeyError tardif.
2. Scopes comparés en JSON canonique ; false/0, true/1 et 0/0.0 restent distincts.
   Une altération de scope d’attestation false→0 sans nouvelle signature est refusée.
3. Transition commune détachée : fuseaux équivalents et microsecondes conservés,
   pas de comparaison flottante ou classement lexical des révisions. Précision
   nanoseconde et horloges fournisseur non qualifiées.
4. Révision vide et null distinctes dans le CSV PG ; guillemets/virgules conservés.
5. Copie défensive à l’entrée des générateurs, y compris mutation du caller pendant
   écriture du stream. Aucune modification du contrat SourceRecord ou des identités.
6. Génération CAS **opt-in** via keyword `expected_snapshot` : omis = chemin brut
   avec garde de date ; `None` explicite = absence attendue ; snapshot = baseline
   attendue. État complet précédent ou cible déjà appliquée, sinon rollback.
7. API `emit_protected_transition` : caches complets, origine contrôlée signée,
   même source/sélection/contexte, émetteurs déjà approuvés, compte anonyme requis.
   Contexte de stockage fourni par le caller, pas vérifié physiquement en DB.
   Aucun import privé/multi-compte activé ni nouvelle confiance implicite.

Le plan reste `executable=false`. La CLI brute n’active pas automatiquement le
CAS ; les vieux SQL n’acquièrent aucune protection rétroactive. Pas de service
Discovery automatisé, pagination/SDK, scheduler, rétention ou migration historique.
[Contrat, API et limites détaillés](../../database/poc/INTEGRITY_CAS_PHASE3.md).

## Qualifications réelles, distinctes des benchmarks précédents

Deux essais **VERIFIED** sur les seuls deux conteneurs temporaires déjà autorisés :
- `attempt-20261028T215506Z-0b4787` : concurrence, CAS, rollback/reprise.
- `attempt-20261028T215853Z-effdf5` : série étendue, **22:58:53–22:58:58 Europe/Paris**.

PostgreSQL 16.15 et SurrealDB 3.3.4, images locales exactes conservées, réseau
interne sans port publié, 2 CPU / 4 Gio / 256 PID chacun ; surveillance du banc.
Nouvelles bases synthétiques, aucune connexion SQL aux POC historiques.
**Aucune restauration ni campagne de performance. Aucun accès Proxmox,
installation, pilote OS, modification système/réseau ou GPU.**

Preuves finales :
- PG : un écrivain en attente de verrou réellement observé ; premier commit,
  second refus CAS malgré une date entrante plus récente.
- Surreal : deux sessions au démarrage coordonné, pause transactionnelle 500 ms,
  un commit et un refus. Pas de mélange partiel des contenus.
- Attente d’absence avec ligne existante : refus ; attente de présence mais ligne
  manquante : refus et aucun ajout résiduel d’une autre ressource du même lot.
- Baseline obsolète avec capture plus récente : refus sur les deux moteurs.
- Baseline réconciliée, rejeu déjà appliqué, rollback après interruption/erreur,
  puis nouvelle tentative : données exactes, pas de perte ni double publication.
- Injection d’un attribut false→0 sans changer le digest déclaré : CAS de ligne
  complète refuse ; seule cette ligne nouvellement créée pour le test est rétablie.
- Révisions nulles/vides et inconnues conservées ; ressource non observée intacte.
- Neuf ressources finales, empreinte normalisée commune :
  `764429f0b25be9a53dbabfd6ab90679239ccccc540b86567fafec1335d47fd78`.

Les délais de synchronisation ne sont pas des latences moteur. Cette qualification
bornée ne prouve pas la charge concurrente prolongée, la disponibilité privée,
les révisions fournisseur ou la sécurité OS. Aucun nouvel usage de benchmark.
Les p50/p95, CPU/RAM/index des séries v5/v6 restent dans les rapports initiaux,
non modifiés et non mélangés avec ces essais fonctionnels.

État final des deux conteneurs temporaires : **exited**. IDs :
- PG `ea3bba2b497fd5160ebada8a3bc751f6a8a0ac999231d2f7a99ccebd0f4c566a`.
- Surreal `b740e2d06ed8fdeba1be53eebd577b72f8235d2fdb430a2cbca838cf060c258c`.
Fingerprints métadonnées POC historiques identiques avant/après, toujours arrêtés.
Ce n’est pas une nouvelle vérification d’intégrité de leurs volumes ou des 405 modèles.

## Chemins des preuves et sécurité de reprise

VM : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/`.
Série finale : `attempt-20261028T215853Z-effdf5`, DB `cas_697d1c6073`,
namespace Surreal `cas_e56618ca48`. Les données/essais précédents sont préservés.
Source exécutée : `code-cas-9ddba473c590/database/poc` ; bundle
`bundle-cas-9ddba473c590.tgz`, SHA256
`d09474dece4f6f9d71955d18409d9809259460e481936979d579ed9a7445bba0`.
Archive `review-cas-9ddba473c590.tgz`, SHA256
`9d55688fea2ea0e147113508e6ff41cc3fd41ae6c5c9a33c6bf8de2091af0ed8`.
Copie durable **privée ignorée par Git** : `database/poc/results/20261028-vm150-cas/`
(18 preuves JSON + manifeste), toutes les tailles/empreintes contrôlées.

La copie défensive et son test ont été ajoutés après la source exécutée ; dix
sorties SQL ont les mêmes empreintes avec le code actuel et le bundle qualifié.
Les tests nouveaux ne sont pas dans ce bundle POC : ils ont été exécutés localement.
Ne pas prétendre avoir exécuté les 615 tests sur la VM.

Aucun credential dans source, fixtures ou export ; `surreal.private.env` reste
privé sur VM, jamais copié. Le mot de passe utilisateur n’est pas mis en document,
variable shell, archive ou ligne de commande. Ne pas modifier l’authentification
ni chercher d’autres credentials. Aucun nettoyage des espaces temporaires.

## Tests et vérifications locales

Lanceur requis : `PYTHONDONTWRITEBYTECODE=1 python3 tests/run_suites.py -q`.

| Suite | Résultat |
|---|---:|
| Discovery | 362 OK (347 existants + 15 nouveaux) |
| Control Plane | 123 OK |
| Infrastructure simulée | 19 OK |
| Isolation applicative | 63 OK, pas un pilote négatif OS |
| Worker | 48 OK |
| Total actuel | **615 succès** |

Tests ciblés après chaque changement important : 32 cas au dernier passage ciblé.
Les anciennes références/attendus ne sont pas modifiés. SHA B3.3 :
`ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
Les checks de secrets et `git diff --check` passent ; index vide.

## Les 34 cases initiales restantes — texte actuel

| Ligne TODO | Case ouverte |
|---:|---|
| 115 | Créer la VM via le script Proxmox |
| 126 | Définir sauvegarde de la VM |
| 138 | Définir et vérifier une sauvegarde/restauration Proxmox de la VM 150 avant d'y stocker des données irremplaçables. |
| 139 | Confirmer la disponibilité courante des healthchecks des deux bases après autorisation : cinq dernières sondes de chaque base réussies avant l’arrêt, mais conteneurs actuellement arrêtés ; aucun démarrage autorisé. |
| 182 | Étendre les sondes à plusieurs modèles et formats ; vérifier les révisions, fichiers, relations et éventuelles restrictions d'accès. L'API sondée ne fournit pas de SHA Git exploitable. |
| 192 | Étendre les sondes à d'autres dépôts et étudier séparément les ressources datasets, spaces, MCP, skills et les modèles servis par l'AI Gateway. |
| 202 | Synchroniser les fichiers locaux non suivis de la VM avec la branche publiée, après comparaison ; voir [la procédure ciblée](database/poc/MOARK_VM_SYNC.md). |
| 203 | Étudier séparément capacités, quotas applicables et dépôts de poids MoArk/Gitee ; aucune association automatique par nom. |
| 215 | Décider la sémantique future des accès/visibilités, de l'isolation domaines/comptes, des révisions et des collectes partielles avant toute évolution de format ou d'identité. |
| 231 | Décider et tester la politique de redirections B1 avant sa migration ; préserver le cas NIM 404 et les limites du SDK. Voir [TRANSPORT_B42.md](database/poc/TRANSPORT_B42.md). |
| 239 | Examiner le prototype et décider multitag NIM, namespaces domaines/comptes, provenance synthétique/réelle et conventions de collecte partielle avant un registre opérationnel. |
| 248 | Examiner le registre manuel avant toute extension online ; provenance synthétique/réelle, domaines/comptes, NIM multitag et résultats partiels restent à décider. |
| 258 | Décider la provenance obligatoire et le contrat d'import avant toute protection complète du B2 brut ; l'option ne remplace pas une validation d'origine. |
| 268 | Définir l'enrôlement/rotation/révocation des émetteurs et la CLI protégée ; HMAC local ne prouve pas une collecte distante. |
| 269 | Raccorder les reçus HTTP conditionnels au moteur budgété, la reprise inter-sources et les politiques de fraîcheur avant de déclarer B4.5 opérationnel. |
| 270 | Définir pagination distante, garanties/quotas SDK, concurrence par hôte et budget global dans des lots séparés ; aucun scheduler. |
| 279 | Valider les contrats d'identité/appairage/bail et l'API de mission avant B5.1 ; développer un faux worker puis autoriser séparément un pilote Linux CPU. |
| 280 | Choisir langage/packaging, stockage durable et politique de clés ; vérifier licences/artefacts exacts, notamment Desktop avant toute redistribution. |
| 281 | Établir une matrice réellement testée par OS/runtime ; aucune capacité GPU/inférence/agent annoncée comme vérifiée par cette étude. |
| 294 | Finaliser la pile HTTP de production et l'isolation OS d'un vrai worker ; les contrôles locaux HTTP/identité/sauvegarde sont validés au checkpoint B5.2, sans exposition LAN. |
| 295 | Définir les contrats agents/rôles/baux réels, appairage/TLS et politiques multi-utilisateurs avant une ouverture LAN ou exécution d'outils ; aucune installation, inférence ou collecte réelle dans B5.1. |
| 307 | Avant un vrai worker : isolation OS éprouvée, politiques réseau/outils/enfants, PKI/appairage/TLS et pile HTTP de production ; conserver le prototype sans IA réelle ni découverte LAN. |
| 317 | Autoriser puis exécuter les tests négatifs OS sur une machine distincte : UID/groupes, secrets/SQLite/objets inaccessibles, FS, réseau, GPU/Docker, CPU/RAM/PID, runtime et arrêt des enfants — **NOT VERIFIED**. |
| 318 | Qualifier le producteur indépendant de permis et fermer/vérifier le réseau OS au port backend ; contrats, observations et canal de refus ajoutés en B5.3.1, sans activation. `--application-test` ne valide pas l'isolation, le filtre IP candidat seul autorise tous les ports loopback. |
| 319 | Avant une inférence ou un outil réel : contrat de lecture des versions d'entrée, quotas cumulés I/O/calcul, politique des moteurs/outils, preuves OS et profils Windows/macOS distincts ; conserver AnythingLLM/Open WebUI facultatifs. |
| 329 | Autoriser un pilote négatif sur une **VM jetable distincte** selon [le plan opérateur Debian](docs/architecture/B53_DEBIAN13_VALIDATION.md), avec confirmations séparées pour comptes, fichiers, unités et pare-feu. Aucun accès à la VM historique autorisé. |
| 330 | Qualifier collecte indépendante, compte exclusif, code/FD/montages, règles/IPv4/IPv6/ports et ressources/arrêt avant un producteur de permis positif. Le contrôleur livré émet toujours `deny` ; strict reste bloqué, OS **NOT VERIFIED**. |
| 331 | Définir si nécessaire une attestation serveur distincte : aucun champ worker ne promeut aujourd'hui le statut `verified`. Pas de vraie inférence, modèle, GPU ou service privilégié permanent. |
| 353 | Finaliser le POC comparatif **PostgreSQL vs SurrealDB** (performances, graphe, vecteurs et contraintes d'exploitation). |
| 365 | Vérifier précisément les contraintes de licence de SurrealDB avant adoption |
| 366 | Décider du moteur principal |
| 367 | Documenter la décision |
| 432 | Industrialiser l'ingestion incrémentale (exécution planifiée, reprise sur erreur, rétention, surveillance) ; le POC B2 est une importation **manuelle**, pas encore un Discovery Service en production. |
| 441 | Éprouver les imports partiellement échoués, les changements de révision réels et les variations de périmètre ; conserver les snapshots et définir la politique de rafraîchissement. |

Les dépendances et classifications sont dans la matrice T01–T35, pas un simple
compteur de travaux de code. G1 Proxmox/backup/restore et G3 OS restent bloqués
sans GO spécifique et environnement jetable distinct. Les POC historiques ne
sont pas autorisés à démarrer. Choix/licence DB, namespaces/révisions et contrats
multi-utilisateurs demandent leurs décisions ; pas d’adoption implicite.

## Prochaines étapes et commandes

- Revoir le chemin CAS et son contrat d’activation avant writer/CLI de production ;
  ne pas rétroactiver le plan non exécutable ou choisir une baseline automatiquement.
- Émetteurs (gestion de confiance/rotation/révocation) et raccordement 304 au moteur
  budgété/fraîcheur/reprise restent les lots logiciels locaux suivants ; ils ne
  nécessitent pas une collecte réelle pour leurs tests, mais leurs décisions de
  confiance doivent rester explicites. Pas de scheduler ou chapitre futur.
- Préparer la décision DB sans la présenter comme déjà approuvée ; aucun nouveau
  benchmark ou restauration nécessaire pour relire les preuves existantes.

```bash
git status -sb
git branch --show-current
git rev-parse HEAD
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.discovery.test_integrity_cas -q
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_suites.py -q
```

Les sockets loopback/Unix de certaines suites nécessitent hors sandbox sous
l’utilisateur courant, pas root. Avant nouvelle qualification VM, lire ses objets
et ressources ; `--cas-only` distingue ce lot des restaurations de `--qualification-only`.
Ne pas relancer automatiquement la VM ou le banc depuis un checkpoint : nouvelle
revue du périmètre/état avant toute exécution, aucune action Proxmox, restauration
ou pilote OS sans autorisation spécifique. Aucun push/merge/commit autorisé ici.

## Git exact après ce checkpoint

Branche `feat/phases-0-3-integrity-cas`, HEAD `5ead5754bd3424356eaf243bf6db271337a8faaa`, main inchangée à la même base, index vide.
**11 fichiers suivis modifiés, 8 fichiers nouveaux non suivis**.
Le fichier [de statut exact](CHECKPOINT_20261028_INTEGRITY_CAS_GIT_STATUS.txt)
inclut ce checkpoint et son annexe. Les données privées sont ignorées, présentes
sur disque et absentes de l’index. La liste n’inclut aucun artefact de campagne.

```text
 M .gitignore
 M TODO.md
 M database/poc/B4_JOURNAL.md
 M database/poc/MANUAL_INCREMENTAL_RUN.md
 M database/poc/REPLAY_GUARD_PHASE3.md
 M database/poc/discovery_cache.py
 M database/poc/discovery_provenance.py
 M database/poc/emit_discovery_import.py
 M database/poc/incremental_import_plan.py
 M database/poc/isolated_docker_bench.py
 M docs/audit/PHASES_0_3_COVERAGE.md
?? database/poc/INTEGRITY_CAS_PHASE3.md
?? database/poc/discovery_import_contract.py
?? database/poc/isolated_cas_qualification.py
?? docs/audit/CHECKPOINT_20261028_INTEGRITY_CAS_GIT_STATUS.txt
?? docs/audit/CHECKPOINT_20261028_INTEGRITY_CAS_PHASES_0_3.md
?? docs/audit/CHECKPOINT_20261028_INVENTORY_PHASES_0_3.md
?? docs/audit/PHASES_0_3_CLASSIFICATION_20261028.md
?? tests/discovery/test_integrity_cas.py
```
