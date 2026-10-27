# B5.3 — worker CPU indépendant, validation OS séparée

## Complément B5.3.1 — 28 octobre 2026

[Audit et bilan](B531_SECURITY_AUDIT.md), [contrat d'isolation](ISOLATION_VERIFICATION_B531.md)
et [banc préparé](../../pilot/worker_isolation/README.md). Base et trois commits B5.3
préservés ; continuation sur la même branche, sans push ni modification de `main`.

Six reproductions ont échoué avant correction : courses des parents en lecture/
création, collision destructive du journal temporaire, double ouverture du verrou,
configuration mutable et helper déclaratif trop permissif. I/O désormais ancrées
sur des descripteurs, validation/verrou sur le même FD, nettoyage par inode créé,
copie de configuration et refus des auto-attestations. Une régression complémentaire
couvre la course des parents lors de l'initialisation CLI.

Le vérificateur collecte les faits Linux bornés et identifie processus, boot,
namespaces, cgroup/inode, configuration et politique ; contrôle demandes/reçus et
canal hérité root avec credentials de **chaque message**. Rechecks avant claim,
calcul et publication/reprise, sans effacer le journal en cas de perte de preuve.
Une entrée JSON ou un reçu structurellement valide ne devient jamais une autorité.
Le contrôleur diagnostique fourni émet uniquement `deny` ; producteur de permis
positifs et qualification OS complète restent bloqués avant le pilote autorisé.

**506 tests Python réussis** : 443 historiques inchangés + 63 nouveaux B5.3.1 ;
Firefox historique réussi. Diagnostic réel en lecture seule et IPC privée réelle
non privilégiée distingués des fixtures. Aucun préparateur/contrôleur root, unité,
règle nftables, compte ou sonde négative OS exécuté : **NOT VERIFIED**.
Le guide Debian indique périmètre, changements proposés, confirmations, contre-épreuves
et retour à l'état initial ciblé. Les sections suivantes conservent le checkpoint
historique B5.3 de 443 tests ; elles ne décrivent pas une validation OS nouvelle.

## Checkpoint historique B5.3

Base publiée vérifiée : `ef5b293ae91132ff0fda0431318b649184e14348` (merge B5.2).
Branche `feat/webui-control-plane-b53`, arbre initial propre. Aucun push, merge,
installation, compte système, changement de permissions hôte ou action sur la VM.

## B5.3a — contrat

`pepeuch.worker/config/v1` distingue ID cluster opaque, UID/GID attendus, UID du
backend, endpoint loopback, capacités, outils et limites. Configuration fermée,
sans credential dans le JSON, sans variable d'environnement secrète. Le premier
exécuteur ne reçoit que le texte de l'objectif approuvé, pas des chemins de fichiers.
La capacité `cpu.text.sha256.v1` désigne un calcul déterministe CPU, pas une IA.

Chaque propriété du rapport `pepeuch.worker/security-evidence/v1` distingue
`declared`, `enforced` et `verified`, avec origine de preuve. Une déclaration,
une authentification API ou un booléen fourni dans la configuration ne suffit pas.
Un profil obligatoire incomplet doit refuser l'exécution.

Les missions, tentatives/générations, epochs de credential, révocation, reprises
manuelles et publication durable B5.2 restent les frontières du protocole.
Le worker historique et son point d'entrée restent disponibles par défaut.

TESTÉ à ce lot : six tests de contrat purs ; aucune preuve d'isolation OS simulée
ne sera présentée comme réelle. La validation système devra être faite sur une
machine distincte explicitement autorisée, pas sur la VM actuelle.

## B5.3b/d/e — parcours autonome et résilience applicative

Entrée explicite `python3 -m pepeuch_worker`, indépendante du répertoire backend.
Initialisation sans écrasement ; `worker.json` et journal privés, fichier credential
séparé 0600/0400, propriétaire courant, régulier, sans lien symbolique ou physique.
Pas de secret en argument, variable d'environnement, configuration JSON ou sortie.
Les imports du point d'entrée excluent SQLite et les modules serveur/persistance.
Le code worker dépend seulement des contrats, du client HTTP et de la bibliothèque
standard. La CLI B5.2 conserve son nom, sa simulation et son répertoire de démo.

L'administrateur crée explicitement une mission par `POST /api/v1/cpu-missions`,
avec le même corps que `/missions`, mais sans fichier autorisé. L'approbation reste
obligatoire. Le routage fixe sélectionne un worker enrôlé avec la seule capacité
`cpu.text.sha256.v1`. Le coordinateur est une règle déterministe, sans LLM.
L'objectif approuvé est haché en UTF-8 ; taille, temps coopératif, outils et sortie
sont bornés. Aucun shell, processus enfant, chemin de fichier, réseau fournisseur,
GPU ou moteur IA dans l'exécuteur. Le livrable markdown contient un rapport JSON
versionné, l'empreinte du texte et son nombre d'octets, pas une analyse de texte.

**Persistance additive sans migration** : l'intention CPU est un événement unique
`mission_execution_contract_v1` avec `details={"capability":"cpu.text.sha256.v1"}`,
créé dans la même transaction que la mission et non modifiable par API. Zéro
événement désigne le contrat historique ; doublon ou contenu inattendu refuse la
lecture. Ce choix conserve les migrations 1/2, leurs empreintes et les sauvegardes
B5.2 ; aucun champ existant n'est détourné. Les projections CPU ajoutent
`required_capability` et distinguent provenance CPU/simulation, sans prétendre
valider le matériel ou l'OS. Une évolution multi-tâches devra versionner ce contrat
explicitement plutôt que déduire une capacité d'un objectif ou d'un nom.

Le protocole `execution-request/v1` / `execution-result/v1` est conservé, avec
admission explicite de la nouvelle capacité et de trois codes CPU. Le validateur
historique reste limité à la démonstration par défaut. Publication : mêmes objets
immuables, quotas, versions, idempotence, générations et epochs B5.2. Le backend
vérifie l'intégrité du livrable ; sa provenance dit `worker_reported_cpu_digest`,
pas preuve indépendante que le calcul a été effectué dans une sandbox.

Le journal `pepeuch.worker/run/v1`, remplacé atomiquement et synchronisé, lie ID
worker, endpoint et empreinte du credential aux opération/tentative/résultat. Une
seule instance possède le verrou local. Le journal contient potentiellement du
texte utilisateur autorisé : conserver son répertoire privé et ne pas le journaliser.
Après perte de connexion ou crash, `--recover` est obligatoire : rejouer la même
demande d'attribution, republier le résultat durable, ou publier une interruption
si aucun résultat n'existe. **Aucun recalcul à la reprise**. Une tentative terminale
est seulement observée. Annulation contrôlée avant et après le calcul ; arrêt
coopératif SIGINT/SIGTERM. Credential renouvelé ou endpoint changé ne peut pas
reprendre un journal actif. Le redémarrage backend conserve son fencing B5.2.

Validation de ce lot : 48 tests B5.3 (unitaires et intégration applicative loopback),
123 tests Control Plane et 272 Discovery Cache historiques inchangés. Sauvegarde,
restauration, anciens objets et révocation des identités restaurées testés aussi
avec une mission CPU. Firefox 158.0.1 : parcours B5.1 complet réussi, texte XSS,
versions, téléchargement/SHA, redémarrage, mobile et déconnexion inclus. Les
changements WebUI rendent les missions CPU explicites ; le formulaire historique
continue de créer des simulations.

## B5.3c/f — candidat Linux et protocole de validation

Gabarits dans `deploy/worker-linux/` : unité manuelle sans installation automatique
ni section d'activation, configuration publique factice. Profil Debian 13/systemd
257/cgroup v2 étudié contre les manpages Debian ; syntaxe rendue et vérifiée avec
le `systemd-analyze` 255.4 disponible ici. Aucun chargement/activation d'unité,
changement de compte, pare-feu, cgroup, périphérique ou permissions hôte exécuté.

Le gabarit propose compte distinct, credentials systemd, aucun privilège, FS strict,
tmp privé, périphériques privés, refus AF_UNIX/socket Docker, restrictions réseau
et CPU/RAM/PID/runtime/arrêt du groupe. **Aucune de ces protections OS n'est validée
par les tests applicatifs.** `inspect` publie observations locales et propriétés
séparées `declared/enforced/verified`. Les preuves obligatoires incomplètes laissent
`run` strict bloqué, avant accès applicatif au credential et connexion. Aucun
fichier d'approbation ou rapport JSON arbitraire ne permet de lever ce refus.

`--application-test` est le mode volontaire des tests fonctionnels, pas une
validation OS. **Ce lot n'offre pas encore un service CPU isolé prêt à activer** :
le vérificateur complet et une politique réseau OS limitée au port backend restent
à implémenter après les essais autorisés. Le réseau loopback du backend est conservé ;
le filtre IP candidat autorise tous ses ports et peut être inopérant sans eBPF.
Un gabarit nftables UID/port est également proposé pour combler ce périmètre,
sans chargement ni validation noyau ; toute expérimentation de pare-feu exige
une autorisation distincte. Pas de purge ou remplacement d'un ruleset existant.

[Contrat complet](WORKER_CONTRACT_B53.md) : identités, entrées, erreurs, reprise,
séparation des preuves et futurs Windows/macOS. [Guide Debian 13](B53_DEBIAN13_VALIDATION.md) :
installation proposée, activation avec refus attendu, protocole négatif OS, test
CPU consenti et retrait ciblé. Les tests OS sont tous `NOT VERIFIED`, sans skip
compté comme succès. Aucun changement de la VM ou des bases POC.

## Bilan de validation

| Ensemble | Résultat | Portée |
|---|---|---|
| Control Plane B5.1/B5.2 | 123 réussis, sources de tests inchangées | Compatibilité applicative et formats historiques |
| Discovery Cache | 272 réussis, fichiers inchangés | Contrats B2/B3/B4, fixtures uniquement |
| Worker B5.3 | 48 réussis | Contrat, CPU, fichiers privés, CLI/imports, intégration HTTP synthétique |
| Total Python | **443 réussis** | Aucune preuve de sandbox OS |
| Firefox existant | Réussi, 158.0.1/geckodriver 0.37.1 | Parcours B5.1, rendu logiciel, données/profils jetables |
| Gabarit systemd rendu | Syntaxe acceptée, systemd 255.4 local | Pas d'installation ni de validation des garanties |
| Isolement OS Debian 13 | **NOT VERIFIED** | Autorisation et machine de test distincte nécessaires |

Empreinte de `reference.b33.json` conservée :
`ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
Revue ciblée : aucune clé réelle dans les fichiers, aucune dépendance/moteur IA,
aucune collecte/import en base ; schémas POC, migrations et fichiers historiques
non modifiés. `git diff --check` requis avant chaque commit local. Pas de push.
Les trois suites ont également été exécutées avec `-v` lors de la validation finale.
Recherche de motifs de clés privées/jetons dans les fichiers changés : aucun
signalement, complétée par la revue des chemins de credentials et des logs.

## Inventaire des fichiers du lot

- `control_plane/` : ajout `capabilities.py` ; extensions de `contracts.py`,
  `execution.py`, `http_api.py`, `service.py`, `worker_client.py`,
  `worker_registry.py`, `workspace.py`, `web/app.js` et `web/index.html`.
- Nouveau package `pepeuch_worker/` : `__init__.py`, `__main__.py`, `contracts.py`,
  `executor.py`, `runner.py`, `private_io.py`, `isolation.py`.
- Nouveaux tests `tests/worker/` : `support.py`, `test_contracts.py`,
  `test_entrypoint.py`, `test_executor.py`, `test_integration.py`, `test_private_io.py`.
- Nouveaux gabarits `deploy/worker-linux/` : `pepeuch-worker-b53.service.in`,
  `worker-config.example.json`, `worker-egress.nft.in`.
- Nouveaux documents `docs/architecture/` : ce journal, `WORKER_CONTRACT_B53.md`
  et `B53_DEBIAN13_VALIDATION.md` ; mises à jour de `README.md` et `TODO.md`.

Points à décider au lot suivant : autorisation du pilote OS, provenance des preuves
de confiance, restriction réseau par port, accès aux versions de fichiers d'entrée,
budget I/O/calcul et contrats de futurs moteurs/outils. Le profil ne doit pas être
promu en production en remplaçant un état inconnu par une déclaration positive.
