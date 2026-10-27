# B3.3 — MoArk : catalogue de modèles servis (27 octobre 2026)

Étude officielle effectuée **avant** le développement. Progression suivie :
fixture synthétique → 15 tests spécifiques → GET anonyme réel → validation B2
→ imports PostgreSQL/SurrealDB → réimportation idempotente sur la VM Debian 13.
**B3.3 est clôturé comme POC validé**, avec un connecteur de métadonnées
opérationnel en lecture seule. L'inférence n'a pas été testée ; le Discovery
Service automatisé reste à développer.

Les résultats VM ci-dessous ont été communiqués par l'utilisateur le
27 octobre 2026. Ils complètent le rapport initial, qui ne recensait que les
artefacts générés localement et indiquait à tort que les imports restaient à faire.

## Surfaces officielles et conditions d'accès

| Surface | Preuve officielle | Qualification B2 |
| --- | --- | --- |
| Catalogue Serverless, `GET /v1/models` (`model.list`) | [OpenAPI](https://moark.ai/v1/yaml), référencée par la [documentation API](https://moark.ai/docs/openapi/v1) | `inference_endpoint` pour une entrée de modèle servi |
| Capacités, `GET /v1/models/capabilities` | Même OpenAPI ; liste conditionnée par les droits du demandeur | Non interrogée ; aucune capacité déduite du nom |
| Inférence texte, image, audio, embeddings, rerank, OCR, vidéo, 3D, etc. | Même OpenAPI et [génération de texte](https://moark.ai/docs/products/apis/texts/text-generation) | Services ; aucun appel d'inférence réalisé |
| Workflows, `POST /v1/workflows/{workflowId}/run`, tâches asynchrones | Même OpenAPI | Contrats distincts à étudier, pas des dépôts de modèles |
| Bibliothèque de modèles, datasets et applications Git/LFS | [Dépôts](https://moark.com/docs/products/models/repositories), [téléchargement](https://moark.com/docs/products/models/download), [datasets](https://moark.com/docs/products/datasets/) | Surface distincte ; aucun `model_artifact` créé par ce connecteur |

La documentation chinoise décrit effectivement le téléchargement de modèles
via Git/LFS et un endpoint adapté aux bibliothèques Hugging Face :
`HF_ENDPOINT=https://hf-api.gitee.com`. Pour les modèles privés elle indique
un jeton personnel Gitee. **Cela ne prouve aucun lien individuel entre un ID
Serverless et un dépôt, un fichier ou un SHA de poids.** Cette surface n'a pas
été sondée ; ne pas fusionner ses identités avec Hugging Face.

La spécification OpenAPI 3.0.3, version déclarée `1.0.0`, téléchargée pour cette
étude avait le SHA256
`4f42e8c275a764dec44e62ac5ad5c1540f3936a052c181b5fdbc53f4b851b5e0`.
Son serveur de production est `https://moark.ai/v1`, alors que le guide de
génération et la configuration de l'interface documentaire proposent aussi
`https://api.moark.ai/v1`. Le connecteur fixe **le premier**, vérifié réellement,
sans repli vers un autre domaine. Les variantes `.com` ne sont pas interrogées
et leur contenu n'est pas assimilé automatiquement à celui de `.ai`.

Pour `GET /models`, la spécification décrit explicitement :

- sans jeton : modèles publics ; avec jeton valide : modèles des forfaits liés
  à ce jeton. Ces deux scopes ne sont donc pas interchangeables ;
- filtres optionnels `vendor`, `type`, et `include_details=false` par défaut ;
- enveloppe `object="list"`, `data[]` ; entrée `id`, `object="model"`,
  `created`, `owned_by`. Les champs optionnels peuvent manquer ;
- `include_details=true` ajoute notamment descriptions, opérations et tarifs.
  Cette extension n'est pas demandée ni normalisée par ce lot.

L'inférence utilise un jeton **Bearer**, créé après connexion à un compte
Gitee/MoArk et autorisé pour les ressources concernées. Le [guide Serverless](https://moark.com/docs/products/apis/)
décrit des forfaits prépayés et une facturation par appel ou tokens. Le
[démarrage](https://moark.ai/docs/getting-started) mentionne 100 appels gratuits
quotidiens par compte ; la [page de prix internationale](https://moark.ai/pricing)
annonce aussi du postpaiement et un crédit initial. Ces pages ne suffisent pas
à établir un quota API gratuit universel, les droits d'un compte donné ou des
limites de débit stables. Aucun compte, achat ou jeton n'a été utilisé. Vérifier
les conditions propres au domaine, au compte et au modèle avant un usage payant
ou périodique. L'accès public à la liste n'accorde pas une licence de poids.

## Contrat conservateur

- `source="moark"`, `entity_type="inference_endpoint"`, `source_id=id` exact
  du modèle dans **l'API officielle `.ai` fixée ci-dessus**. Cette identité
  désigne l'offre servie, pas un modèle canonique ni un URL de dépôt.
- Clé B2 calculée par le mécanisme existant `(source, entity_type, source_id)`.
  Une éventuelle autre plateforme/domaine devra avoir un contrat d'identité
  explicite avant extension ; ne pas rendre le domaine configurable aveuglément.
- `source_revision=null` : `created` est un timestamp, pas une révision.
- `owned_by`, s'il est présent, reste un label fournisseur, sans lien de parenté.
- `access="unknown"`, `license=null`, `weights_available=null` : le listing
  public ne prouve ni appel possible, ni droits, ni disponibilité des poids.
- `relationships=[]` : aucun rapprochement automatique avec HF, ModelScope,
  CSGHub ou une bibliothèque Gitee, même en cas de noms identiques.
- Copie de l'entrée sélectionnée dans `raw_metadata`, URL du catalogue et base
  API dans `attributes`, périmètre et observation dans le snapshot B2.
  Les entrées non sélectionnées ne sont pas importées.
- Rejet des identités incorrectes, doublons, enveloppes inattendues, pagination
  non prise en charge, valeurs non finies et clés de secrets dans toute la réponse.
  Une absence dans cette liste partielle ne signifie pas une suppression.

## Fixtures et tests hors ligne

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -q
python3 database/poc/probe_moark.py \
  --fixture database/poc/fixtures/moark_models.synthetic.json \
  > /tmp/moark-SYNTHETIC-DO-NOT-IMPORT.json
```

La fixture est inventée, y compris propriétaire et timestamp ; **ne pas
l'importer comme observation réelle**. Son scope porte
`input="synthetic_fixture"`, distinct du scope `input="public_api"` de la sonde.
Les tests couvrent séparation d'identités, inconnues, sélection exacte, absence,
doublons, secrets, métadonnées brutes, déterminisme B2, générateurs PG/SurrealDB,
GET borné, refus HTTP/redirections et absence de snapshot après échec.

## Sonde réelle et validation

```bash
python3 database/poc/probe_moark.py --online --model-id Qwen3-8B \
  > /tmp/moark-live.json
```

Un seul GET de
`https://moark.ai/v1/models?type=text2text&include_details=false`, sans
authentification, cookies, redirections ou retries ; timeout 20 secondes,
réponse limitée à 2 Mo. Le fournisseur ne propose pas de filtre par ID dans
ce contrat : la liste filtrée est lue puis **une seule entrée exacte** retenue.
Les HTTP 401/403/429 et autres erreurs arrêtent la sonde sans contournement,
corps d'erreur ni snapshot sur stdout. Aucun appel de génération ou téléchargement.

Observation réelle du **27 octobre 2026 à 13:12:32 UTC** :

```json
{"created":1759045378,"id":"Qwen3-8B","object":"model"}
```

`owned_by` est réellement absent et reste `null`. Validation du contrat de
source, de l'ID exact, du scope anonyme, des empreintes B2 et des valeurs inconnues
effectuée. Snapshot réel :
`s_51daa58e4b13fd2c6098dad5423ccc29064a8dc99e9f4687066d6f134394530e`.
Clé de l'unique ressource :
`d_31660a86045ce9e8dcc6ae12de526fd8c3717ef4f0c260676824a7fd8a3f28b1`.
La disponibilité d'inférence et la licence ne sont **pas** validées par ce GET.

## Imports et réimportation validés sur la VM

| Vérification | Résultat communiqué pour Debian 13 |
| --- | --- |
| Suite Python complète | 91 tests réussis |
| Sonde anonyme `Qwen3-8B` | Snapshot réel ci-dessus validé |
| `poc.discovery_cache` PostgreSQL | 14 ressources |
| `discovery_cache` SurrealDB | 14 ressources |
| Catalogue historique PostgreSQL | 405 modèles préservés |
| Réimportation du même snapshot | Idempotence confirmée |

Les imports ont été exécutés sur la VM. Ces résultats valident le parcours de
métadonnées et les imports manuels ; ils ne prouvent ni appel d'inférence
possible, ni droits d'utilisation du modèle, ni disponibilité des poids.
La conservation du catalogue historique PostgreSQL est confirmée ; aucun
nouveau résultat sur le catalogue historique SurrealDB n'est déduit de ce bilan.

### Procédure de reproduction

Les générateurs B2 existants acceptent déjà `inference_endpoint` : aucune
migration ou modification des tables historiques n'est nécessaire. Après
inspection du snapshot **réel** :

```bash
python3 database/poc/emit_discovery_import.py --engine pg \
  --snapshot /tmp/moark-live.json > /tmp/moark-live.pg.sql
python3 database/poc/emit_discovery_import.py --engine surreal \
  --snapshot /tmp/moark-live.json > /tmp/moark-live.surql
```

Conserver les trois artefacts hors Git dans le répertoire de travail choisi.
Les imports générés sont bornés à `discovery_cache` et utilisent les upserts B2
existants, sans suppression des entrées absentes ni modification du schéma des
bases historiques. La procédure ci-dessous permet de reproduire la validation ;
elle n'est pas une nouvelle action nécessaire à la clôture B3.3.

Sur la VM, depuis `/opt/pepeuch-ai/repo`, après y avoir transféré et inspecté
les trois artefacts réels (adapter les chemins si nécessaire) :

```bash
# Le répertoire est déjà monté dans /data par le Compose du POC.
cp /tmp/moark-live.surql /opt/pepeuch-ai/data/surreal-poc/moark-live.surql

# Valider SurrealQL avec la version du POC avant toute écriture.
sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml \
  exec -T surrealdb /surreal validate /data/moark-live.surql

# Relever au préalable les totaux et la présence éventuelle de la clé MoArk.
sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
  exec -T postgres psql -X -v ON_ERROR_STOP=1 -U pepeuch_ai -d pepeuch_ai \
  < /tmp/moark-live.pg.sql

sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml \
  exec -T surrealdb /surreal import \
  --endpoint http://127.0.0.1:8000 --namespace pepeuch_ai --database poc \
  /data/moark-live.surql
```

Suivre les [contrôles B2](DISCOVERY_CACHE_B2.md#b-import-explicite-après-inspection) :
lecture de la ressource par clé, contrôle des métadonnées brutes et des inconnues,
réimportation du même snapshot et comparaison des totaux et empreintes.
Lors de la clôture B3.3, les deux moteurs contiennent 14 ressources après
réimportation, avec les 405 modèles historiques PostgreSQL préservés. Une
réexécution sur le même périmètre ne doit pas ajouter de doublon. D'autres lots
peuvent ensuite augmenter les totaux ; toujours relever l'état initial.
SurrealDB applique `/import` instruction par instruction, sans rollback global.

La synchronisation des fichiers locaux de la VM avec la branche publiée est
documentée séparément dans [MOARK_VM_SYNC.md](MOARK_VM_SYNC.md). Elle ne relance
ni collecte réseau ni import en base.
