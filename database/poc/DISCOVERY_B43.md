# B4.3 — registre et CLI manuelle sur fixtures

Les sept contrats sont reliés à leur `SourceSpec` dans `discovery_registry.py`.
`discover_sources.py` fournit une entrée commune **exclusivement sur fixtures**.
Elle n'a aucun mode online, client de base ou import. Les CLI historiques restent
disponibles avec leurs options existantes ; leurs modes réseau ne sont pas utilisés
par ce registre.

## Utilisation hors ligne

Depuis la racine du dépôt :

```bash
# Description des sept sources ; aucun adaptateur/SDK/fixture chargé.
python3 database/poc/discover_sources.py --list-sources

# Exécution explicite des sept fixtures, sortie B2 JSON uniquement sur stdout.
python3 database/poc/discover_sources.py --fixtures \
  > /tmp/discovery-B43-SYNTHETIC-DO-NOT-IMPORT.json

# Une source ou un sous-ensemble explicite ; options répétables.
python3 database/poc/discover_sources.py --fixtures --source huggingface
python3 database/poc/discover_sources.py --fixtures \
  --source csghub --source moark
```

Sans `--fixtures` ou `--list-sources`, la commande échoue à l'analyse des arguments.
`--online` n'existe pas. La commande ne produit ni SQL ni SurrealQL et ne relie
aucun appel de collecte réelle. La mention **SYNTHETIC, do not import** est envoyée
sur stderr ; stdout reste un snapshot B2 compatible, sans ajout de champ susceptible
de changer les empreintes historiques.

Ces données sont des exemples de test, **pas de nouvelles observations fournisseur**.
Ne pas importer ces résultats comme données réelles. L'absence d'un indicateur
synthétique universel dans les anciens payloads B2 reste une limite connue ; ce
lot fournit un manifeste explicite hors payload et ne migre pas les anciens scopes.

## Manifeste et sélection

Le manifeste par défaut est `fixtures/discovery_b43.synthetic.json`. Il déclare
`format=pepeuch-ai.fixture-discovery/v1`, `synthetic=true`, un horodatage fixe et
les entrées des sept sources. Les fixtures B3 et B4.0 sont réutilisées à l'identique.
Le runtime ne lit **jamais** `reference.b33.json` ni un module de tests.

Chaque entrée contient un chemin de fixture relatif au répertoire du manifeste,
un scope existant, une révision de catalogue lorsque nécessaire et éventuellement
une clé d'extraction du payload JSON partagé. `--manifest` permet de fournir une
autre configuration locale explicitement synthétique ; les chemins absolus,
traversées `..` et symlinks vers les fixtures sont refusés. Les fichiers JSON sont
lus avec une limite de 2 Mo et le parseur strict commun. Les TOML sont lus par le
collecteur historique local.

L'horodatage fixe par défaut est `2026-10-27T00:00:00+00:00`. L'option
`--captured-at` peut le remplacer ; elle change la date d'observation, pas l'identité
du snapshot si les faits et le scope restent égaux. Aucun commit Git ni timestamp
fournisseur n'est inventé pour remplir une révision absente.

Le scope est contrôlé contre SourceSpec et les règles déjà déclarées :

| Source | Liaison de fixture | Sélection et contrôles |
| --- | --- | --- |
| models.dev | `collect_modelsdev` | TOML locaux triés, limite explicite, commit synthétique épinglé ; pas de commande Git |
| huggingface | `normalize_huggingface_model` | Un ID exact par fixture ; ID de sortie identique à la sélection |
| awesome-ai-agents | `normalize_awesome_catalog` | L'entrée existante est placée dans un catalogue synthétique d'une entrée, puis normalisation/déduplication et limite ; SHA de catalogue explicite |
| nvidia-nim-metadata | `normalize_nvidia_nim_metadata` | resourceId et tag exacts dans le scope ; identité toujours fondée sur resourceId seul |
| modelscope | `normalize_modelscope_repo` | RepoInfo JSON de fixture, ID et domaine documenté ; aucun SDK importé ou appelé |
| csghub | `normalize_csghub_model` | ID exact, endpoint officiel, source csg et révision demandée main ; aucun GET |
| moark | `select_moark_model` | Roster synthétique puis ID exact ; domaine/API fixés, scope anonymous/synthetic_fixture ; aucune inférence |

Les types de sortie et la nullabilité des révisions sont vérifiés par la liaison
contre SourceSpec. Les normaliseurs gardent leurs règles métier. Aucun nom de
fonction, module ou plugin n'est résolu depuis le JSON. Les imports d'adaptateurs
sont tardifs ; le module descriptif, le registre, `--help` et `--list-sources`
n'importent pas les SDK optionnels.

Le lot traite les fixtures existantes avec **un ID par fixture** pour les modes
`exact_ids`. Il ne promet pas une collecte batch distante ni un catalogue agents
complet. Les champs de scope inconnus, sources inconnues/répétées, correspondances
d'identité incorrectes et fausses provenances sont refusés. Les comptes et domaines
nouveaux nécessitent toujours une décision explicite de namespace.

## Échecs et compatibilité

Le snapshot est construit et validé avant la première écriture stdout. Si une
source demandée manque ou échoue, aucun snapshot partiel n'est émis : code de
retour 1 et résumé d'erreur sans contenu sensible. Une sélection explicite d'un
sous-ensemble possède son propre scope ; l'ordre des sources ne change pas
l'empreinte. Il n'y a ni omission silencieuse d'une source en échec ni suppression.

Les tests de lecture HTTP interrompue couvrent `IncompleteRead`, connexion coupée
et timeout pendant `response.read()`. Un test utilise aussi le parseur HTTP réel
de la bibliothèque standard sur un flux en mémoire : `read(n)` peut rendre un
corps tronqué sans exception. `Content-Length` est donc contrôlé lorsqu'il existe ;
une longueur incohérente est refusée et une longueur annoncée excessive est
rejetée avant lecture. Les headers absents restent acceptés pour les réponses
sans longueur annoncée, sous la limite existante de lecture et de JSON.

La réponse est fermée, aucun préfixe même JSON valide n'est décodé après une
lecture incomplète, aucune tentative supplémentaire n'est effectuée. Le client
commun traduit `IncompleteRead` en `MetadataNetworkError`, sans octets partiels
ni détail sensible dans le diagnostic. Les CLI utilisant ce client conservent
leur chemin d'échec sans snapshot.

Validation : **167 tests réussis** (146 précédents + 3 tests de lecture/framing
HTTP avec variantes + 18 tests registre/CLI). Les sept snapshots individuels
correspondent intégralement aux valeurs B3.3 figées : SourceRecord, raw_metadata,
relations, record_key, payload_sha256 et snapshot_id. Le snapshot agrégé conserve
`s_e1ea910f305c35e27a63aa1a911c028ac5c0a4c2ca98b46ff5c66e9674ee5a60`.
Les fichiers de référence n'ont pas été régénérés.

Les exécutions CLI de test ont lieu dans des interpréteurs isolés interdisant
connexions, résolution DNS, subprocessus de collecte, imports de SDK/clients de
base et ouverture du JSON d'attendus. Les trois CLI B3 sont aussi testées sur leurs
fixtures et comparées aux références hors date d'observation ; les CLI B1/B2
conservent leurs tests existants et leur aide. Aucun appel réel ou import en base
n'a été effectué.

## Suite différée

Le registre online, les garanties de redirection B1, le contrôle réseau du SDK,
les budgets/retries, checkpoints et résultats partiels ne sont pas ajoutés ici.
Le Personal Model Catalog et les schémas PostgreSQL/SurrealDB restent inchangés.
