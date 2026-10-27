# B4.0 — Caractérisation des sept contrats Discovery Cache

Référence publiée : `d528580ddd6e1c4b364b64e2322eb2649e7b2e62` (B3.3).
Lot de caractérisation uniquement : aucun adaptateur, transport, générateur,
schéma de base ou contrat métier modifié. État initial : **91 tests réussis**
sur une extraction isolée du commit publié. B4.0 ajoute **17 tests**.

Ce document décrit la référence B3.3 et le lot B4.0 historique. Depuis B4.1,
les données sont copiées défensivement et le JSON est décodé strictement ; voir
[PRIMITIVES_B41.md](PRIMITIVES_B41.md). Les valeurs sérialisées figées restent
inchangées, y compris les observations historiques d'aliasing dans le JSON.

Les types ci-dessous décrivent des ressources découvertes. `model_artifact`
désigne les métadonnées d'un dépôt de modèle, sans certifier le téléchargement
effectif des poids. Une référence, un agent, un microservice et une offre
d'inférence conservent chacun leur type ; aucune admission au catalogue personnel.

## Matrice des identités, sélections et révisions

| Source / type | Identité et namespace B2 | Sélection actuelle | Révision et provenance |
| --- | --- | --- | --- |
| `models.dev` / `model_reference` | Chemin `provider/model` relatif à `models/`, sans `.toml` ; namespace `models.dev` | Premiers N chemins triés du submodule ; 5 par défaut, 0 = tous | Commit Git du catalogue ; CLI refuse checkout sale ; `source_path` et TOML brut converti en JSON |
| `huggingface` / `model_artifact` | `id` exact du dépôt ; namespace `huggingface` | Deux IDs fixes dans le collecteur B2 ; normaliseur unitaire ; contrôle de correspondance dans le collecteur | `sha` si présent, actuellement chaîne non vide sans contrôle de longueur ; JSON API brut |
| `awesome-ai-agents` / `agent_resource` | `agents[].id`, pas le nom du projet ; namespace dédié | Commit de `main` résolu, JSON à ce commit ; validation/déduplication complète puis premiers N IDs uniques, 3 par défaut, 0 = tous | Commit Git SHA-1 minuscule de 40 caractères obligatoire ; entrée JSON brute avec ses liens sources |
| `nvidia-nim-metadata` / `nim_microservice` | **`resourceId` seul**, namespace NIM ; tag exclu de l'identité | Un `resourceId` + tag exacts ; profil matériel utilisé seulement par l'audit hors normalisation | Tag de conteneur **mutable**, pas un digest ni commit ; réponse API brute et détails de release |
| `modelscope` / `model_artifact` | `owner/name` demandé, vérifié dans RepoInfo ; namespace `modelscope` | Sonde d'un dépôt `repo_type=model`, domaines `.cn` ou `.ai` explicitement proposés ; séparée de B2 `--include-online` | SHA explicite complet 40/64 hex si présent, sinon null ; date/branche/ID numérique ne sont pas des révisions ; `RepoInfo.to_dict()` normalisé JSON |
| `csghub` / `model_artifact` | `namespace/name` exact ; namespace `csghub`, source amont **csg** | Sonde d'un dépôt, domaine `hub.opencsg.com`, branche demandée `main` ; pas de miroir hf/ms/xet | SHA explicite complet 40/64 hex si présent, sinon null ; JSON API brut ; branche demandée dans le scope |
| `moark` / `inference_endpoint` | ID opaque de l'offre servie dans l'API `.ai` fixée ; namespace `moark` | GET du roster public `type=text2text&include_details=false`, puis un ID exact ; pas de filtre ID distant dans ce contrat | **null** : `created` est un timestamp ; entrée sélectionnée brute, base API et URL du catalogue conservées |

L'identité de toutes les sources est
`d_ + SHA256(JSON([source, entity_type, source_id]))`. La révision, le nom
d'affichage et le contenu n'en font pas partie. Les empreintes de payload et de
snapshot sont distinctes. Le scope décrit la sélection et ne doit pas inclure
un commit mouvant à la place de `source_revision`. `captured_at` n'entre pas
dans le calcul de `snapshot_id`. Un nom similaire ne prouve aucun lien.

## Matrice des valeurs, accès et relations

| Source | Accès, visibilité et licence actuels | Formats et inconnues | Relations conservées |
| --- | --- | --- | --- |
| `models.dev` | `open_weights` tri-état ; aucun champ `access` ni licence normalisé par ce collecteur ; autres données dans le brut | Booléen absent/invalide → null ; contexte absent/invalide → null ; listes weights/benchmarks absentes → compteurs 0 ; aucun format inféré | Aucune ; le segment fournisseur de l'ID n'est pas une fusion canonique |
| `huggingface` | `gated=false` → public, true/auto/manual → gated ; absent → unknown ; `approval_mode` distinct ; licence `cardData.license` ou null ; `private` n'est pas normalisé | Architectures/base_models/fichiers absents → null ; fichiers vides → 0 ; `available_formats=[]` signifie aucune observation positive, même si fichiers absents ; gguf/safetensors observés par métadonnées ou noms de fichiers | Seulement `declared_base_model`, cible dans le namespace HF, depuis `cardData.base_model` |
| `awesome-ai-agents` | `has_public_repository` booléen ou null : ne vaut pas autorisation de modèle ; licence non normalisée | Catégories et sources absentes → null ; sources vides → `[]` et compteur 0 ; champs/compteurs inconnus restent bruts | Pas de relation de modèle ; URL de projet conservées comme attributs |
| `nvidia-nim-metadata` | `registry_entitlement=unknown` ; ni licence ni accès NGC déduits du catalogue | Profils absents → null / compteur null ; profils vides → [] / 0 ; `tested_gpu_devices=[]` accepté mais champ obligatoire pour un profil ; false et contexte 0 conservés ; contraintes numériques finies ; noms/SHA opaques non interprétés | Aucune ; profils de microservice et contraintes ne prouvent pas une identité HF ni une exécution GPU |
| `modelscope` | Visibilité 1/3/5 → private/internal/public ; `private` et visibilité contradictoires refusés ; public + gated=true refusé ; `access` encore dérivé de visibilité/gating ; licence explicite ou null | Tags absents → null ; chaînes optionnelles vides → null ; `files=null` même si dépôt public ; aucun format observé | Aucune relation HF déduite |
| `csghub` | `private=false` → visibilité publique mais accès unknown si gating absent ; `private=true` → accès private ; licence explicite ou cardData, conflit refusé ; un tag `apache-2.0` ne suffit pas | Fichiers absents → compte/observed_formats null ; vides → 0/[] ; formats seulement via noms de fichiers ; compteurs absents → null | Aucune relation HF/ModelScope déduite ; ressources d'agents et gateway non étudiées par ce contrat |
| `moark` | `access=unknown`, `license=null`, `weights_available=null` ; listing public ≠ droit ni appel d'inférence validé | `owned_by` et `created` optionnels → null ; aucun poids/format/capacité inféré ; extensions éventuelles restent brutes | Aucune relation avec dépôts Gitee/HF/ModelScope/CSGHub déduite |

Le brut garde les champs inconnus. Les B3 en font une copie JSON ; les
normaliseurs HF/agents/NIM partagent encore la structure d'entrée à B3.3.
`SourceRecord(frozen=True)` ne fige pas les dicts imbriqués. Les tests B4.0
caractérisent cet aliasing **sans le corriger** : les snapshots partagent aussi
attributes/raw/scope avec les objets passés à `make_snapshot`. Une mutation
ultérieure peut invalider leur empreinte ; `validate_snapshot` la détecte.
Les opérations validation/comparaison/génération SQL elles-mêmes ne mutent pas
les snapshots. Une sérialisation JSON relue constitue une copie indépendante.

## Transports et erreurs existants

| Surface | Transport effectif | Particularités à préserver |
| --- | --- | --- |
| models.dev | Fichiers locaux TOML + Git en CLI ; aucune requête dans le collecteur local | Checkout sale/ref non valide/TOML invalide : échec ; commit explicitement passé aux tests pour éviter toute dépendance Git des fixtures |
| HF, agents, NIM | `get_json` commun B1 : urllib, Accept JSON, User-Agent, taille 3 Mo ; timeout CLI 1–60 s, 20 s par défaut | Politique de redirection urllib actuelle, sans allowlist commune ; racine dict requise ; pas de retry ; erreurs non NIM remontent ; logs B2 peuvent encore inclure `str(exc)` |
| NIM spécifiquement | Même GET B1 sur `api.ngc.nvidia.com` | HTTP 404 = métadonnées indisponibles pour **ce tag**, pas suppression de modèle ; source omise, avertissement ; autres codes remontent |
| ModelScope | SDK officiel chargé seulement en mode online, `get_repo()` puis `to_dict()` | Aucun timeout/retry explicitement imposé par cette sonde ; sonde ne configure pas de jeton mais le comportement SDK/environnement n'est pas garanti anonyme ; erreurs SDK journalisées par type ; erreur de contrat ensuite peut inclure un message |
| CSGHub | urllib standard, GET officiel fixe, redirections interdites, 2 Mo, timeout 20 s | Validation d'identité avant réseau ; erreur sans corps/source sensible ; pas de retry ; fixture ou online explicites |
| MoArk | urllib standard, un GET fixe, redirections interdites, 2 Mo, timeout 20 s, anonyme sans cookies | Codes HTTP imprimés sans corps ; pas de retry ; roster/identité/type/doublon/pagination inattendus refusés ; aucune inférence |

Les parseurs JSON courants ne rejettent pas uniformément les clés répétées.
La compatibilité ne signifie pas qu'un JSON ambigu doit être accepté à l'avenir :
le durcissement du parsing devra avoir ses tests et sa décision de périmètre.
Les différences HTTP/SDK et le 404 NIM restent des règles propres aux sources.

## Références figées et méthode de capture

`fixtures/contracts_b40/reference.b33.json` contient **des valeurs littérales** :
sept payloads `SourceRecord` complets, leurs `record_key`/`payload_sha256`, sept
snapshots à scopes fixes, un snapshot agrégé (ID + ordre des clés), une
comparaison partielle et les observations de partage mémoire B3.3.

SHA256 du fichier de référence :
`ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
Snapshot synthétique agrégé :
`s_e1ea910f305c35e27a63aa1a911c028ac5c0a4c2ca98b46ff5c66e9674ee5a60`.
Ce n'est **pas** le snapshot réel MoArk importé sur la VM.

Capture réalisée une seule fois hors des tests :

1. `git archive d528580ddd6e1c4b364b64e2322eb2649e7b2e62 database/poc`,
   extrait dans un nouveau répertoire temporaire.
2. Exécution des 91 tests sur ce code isolé : succès.
3. Normalisation des entrées avec les **modules de l'archive** ; chemins des
   modules vérifiés, SHA256 des huit modules concernés consignés dans le JSON.
4. Fixtures B3 réutilisées à l'identique. Exemples B1 déjà présents dans les tests
   copiés en données JSON pour HF/agents/NIM ; deux petits TOML synthétiques pour
   le collecteur models.dev. Aucun événement fournisseur réel ajouté.
5. Horodatage fixé à `2026-10-27T00:00:00+00:00` et scopes déclarés dans le JSON.
   Écriture des résultats puis lecture seule par les tests futurs.

Ne pas régénérer les attendus à partir de l'implémentation courante pour faire
passer un test. Examiner toute différence. La comparaison de JSON canonique
utilisée par les tests distingue aussi `false` de `0`, contrairement à certaines
comparaisons Python. L'ordre d'entrée des sept sources ne change pas le résultat
trié du snapshot agrégé. Les tests bloquent connexions et résolution DNS.

## Collectes partielles et cas NIM multitag

Les tests retirent l'observation MoArk d'un snapshot synthétique de même scope :
une seule entrée `not_observed`, aucun ordre de suppression. Les générateurs
émettent uniquement les upserts des ressources présentes, sans toucher les
tables historiques. Les scopes différents sont refusés par le comparateur et
un snapshot entièrement vide est refusé par `make_snapshot`.

**NIM : plusieurs tags d'un même `resourceId` ne sont pas pris en charge dans
un même snapshot.** Les deux enregistrements ont la même identité et des
payloads différents ; `make_snapshot` lève `Conflicting records`. Le doublon
strictement identique est dédupliqué. B4.0 conserve cette règle. Changer le tag
de sélection change aussi le scope de collecte : stabilité de clé n'autorise
pas à comparer artificiellement deux périmètres différents.

## Décisions avant B4.1 et lots suivants

- Mutualiser les types seulement si leurs contrats sont réellement identiques :
  chaînes vides, compteurs, valeurs optionnelles et accès diffèrent selon la source.
- Étendre la protection récursive des secrets : listes de clés et normalisation
  différentes entre B3 ; pas de barrière équivalente dans les B1. Ne pas créer
  de fixture contenant un vrai secret pour vérifier cette protection.
- Définir l'isolation des données en mémoire sans changer les payloads B2 :
  copie défensive des bruts et des snapshots ; suivre séparément les observations
  historiques d'aliasing et les garanties futures souhaitées.
- Versionner ou placer hors payload les futures conventions synthétique/réel,
  nature/granularité de révision et compte/domaine d'accès. MoArk distingue
  fixture/public_api dans scope ; les sondes ModelScope/CSGHub ne le font pas.
- Ne pas changer en passant les clés NIM, ni généraliser `--endpoint` : domaines
  et comptes ne sont pas inclus dans les clés actuelles ; isolation à concevoir
  explicitement avant ajout d'installations ou périmètres authentifiés.
- Définir un décodage JSON strict et des erreurs sans données sensibles ; un
  durcissement de rejet des entrées invalides doit être documenté séparément.
- Formaliser réussite partielle/échec/absence/304 et checkpoints avant un
  incrémental ; aucune omission ne doit devenir une suppression.

Les écarts ci-dessus sont des limites existantes, pas des régressions B4.0.
Le lot conserve les 91 tests historiques et toutes les références sérialisées.
Voir [B4_JOURNAL.md](B4_JOURNAL.md) pour la progression des lots suivants.
