# B2 — Discovery Cache POC, PostgreSQL + SurrealDB (27 octobre 2026)

Objectif : *mémoriser ce qui a été découvert*, sans remplir encore le
**Personal Model Catalog**, sans télécharger de poids et sans dépendre du GPU.
Les scripts génèrent des fichiers et **ne modifient jamais eux-mêmes une BD**.
La mise à jour des POC doit être lancée explicitement après inspection.

## Contrat commun

Le snapshot JSON `pepeuch-ai.discovery-cache/v1` conserve :

- `scope` : sources interrogées et limites de sélection, **sans** révision mouvante ;
- `captured_at` : horodatage UTC de l'observation ;
- `snapshot_id` : empreinte déterministe de la sélection et de ses contenus ;
- `records[]` : `record_key`, `payload_sha256`, `source`, `entity_type`,
  `source_id`, `source_revision`, `display_name`, `attributes`,
  `relationships`, `raw_metadata`.

**Identité stable** : `SHA256(source, entity_type, source_id)` avec séparation
sans ambiguïté par sérialisation JSON. Le SHA de contenu couvre aussi la
révision et les métadonnées. Une révision qui change sans renommer le dépôt
fait évoluer le contenu, **pas** l'identité logique.

Les imports écrivent seulement dans `poc.discovery_cache` (PostgreSQL) ou
`discovery_cache` (SurrealDB, base `pepeuch_ai/poc`). Les tables de l'ancien
POC `poc.external_models`, `external_models` et leurs 405 modèles ne sont
ni écrasées, ni purgées. Aucun catalogue personnel n'est créé.

Un import n'efface jamais une entrée absente. Il actualise `last_seen_snapshot`
et `last_seen_at` des entrées observées. Un `not_observed` lors de la comparaison
**n'est pas une suppression** : la collecte est souvent partielle.

La preuve de non-changement repose sur le même `payload_sha256`, pas sur
une comparaison de timestamps. Le `snapshot_id` peut rester identique entre
deux collectes faites à des heures différentes si les faits sont inchangés.
Les commits et SHA propres à chaque source sont dans `records[].source_revision`,
et leur évolution est donc comparée même si la sélection (`scope`) ne change pas.

## Sources reconnues

| Source | Domaine du contrat | Intégration B2 |
| --- | --- | --- |
| `models.dev` | `model_reference` | Import local, submodule épinglé |
| `huggingface` | `model_artifact` | Deux dépôts publics, opt-in réseau |
| `awesome-ai-agents` | `agent_resource` | 3 ressources par défaut, opt-in réseau |
| `nvidia-nim-metadata` | `nim_microservice` | Un microservice/tag, opt-in réseau |
| `modelscope` | `model_artifact` | Type prêt, **adaptateur à étudier** |
| `csghub` | `model_artifact` ou `agent_resource` | Type prêt, **adaptateur à étudier** |
| `moark` | `inference_endpoint` | Type prêt, **adaptateur à étudier** |

Références officielles de la prochaine étude :

- ModelScope : https://github.com/modelscope/modelscope_hub
- OpenCSG / CSGHub : https://github.com/OpenCSGs/csghub et https://www.opencsg.com/docs/en/csghub/101/introduction
- MoArk : https://moark.ai/docs/

**Important** : le fait qu'une plateforme soit compatible Hugging Face ne
prouve pas qu'elle sert le même fichier ou la même révision. Pas de fusion
canonique sur la seule similitude des noms.

### Lot de compatibilité à planifier (après B2)

1. **ModelScope** : sonder l'API officielle de métadonnées d'un dépôt modèle
   connu ; conserver le `model_id`, sa révision, la licence, les fichiers,
   les éventuelles restrictions d'accès et les liens de parenté *explicites*.
   Les datasets, Studios, agents et MCP ne deviennent pas automatiquement des
   `model_artifact` : chaque famille réclame un contrat adapté.
2. **OpenCSG / CSGHub** : vérifier la forme et la version des réponses de son
   API, la compatibilité déclarée avec Hugging Face et les identifiants réels
   des variantes. Séparer modèles et ressources d'agents ; conserver l'origine
   de chaque relation croisée, sans dédupliquer sur le nom.
3. **MoArk / OSChina** : vérifier d'abord le périmètre de son catalogue, les
   méthodes d'authentification et les conditions d'usage. Un modèle **servi**
   par API doit être représenté comme `inference_endpoint` ; ne créer une fiche
   `model_artifact` que si un dépôt de poids et une provenance sont prouvés.

Pour chaque source : commencer par **une sonde ciblée en lecture seule** et
ses tests de contrat sur fixtures, sans compte requis si un endpoint public
existe. Les quotas, les droits et les données de licence devront être vérifiés
avant tout collecteur périodique. Ne jamais confondre `unknown` et `false`.

## A. Validation hors ligne

Depuis `/opt/pepeuch-ai/repo` :

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -v

mkdir -p /opt/pepeuch-ai/data/discovery-poc

python3 database/poc/collect_discovery_snapshot.py \
  --models-limit 5 \
  > /opt/pepeuch-ai/data/discovery-poc/local5.json

python3 database/poc/emit_discovery_import.py \
  --engine pg \
  --snapshot /opt/pepeuch-ai/data/discovery-poc/local5.json \
  > /opt/pepeuch-ai/data/discovery-poc/local5.pg.sql

python3 database/poc/emit_discovery_import.py \
  --engine surreal \
  --snapshot /opt/pepeuch-ai/data/discovery-poc/local5.json \
  > /opt/pepeuch-ai/data/surreal-poc/discovery-b2-local5.surql
```

L'échantillon local de **5** modèles permet de vérifier les générateurs avant
d'autoriser le moindre import. Les fichiers d'artefacts restent dans `/opt/pepeuch-ai/data/`,
et non dans Git. Répéter la collecte avec le **même** `--models-limit` pour
comparer deux snapshots de même périmètre.

Le contenu SQL peut être contrôlé avec `sed -n '1,12p' fichier.sql` et
`/surreal validate /data/discovery-b2-local5.surql` avant import. Les données
ne sont jamais envoyées automatiquement à une base.

## B. Import explicite après inspection

Sur PostgreSQL, créer **seulement la nouvelle table** :

```bash
sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
  exec -T postgres \
  psql -X -v ON_ERROR_STOP=1 -U pepeuch_ai -d pepeuch_ai \
  < database/poc/postgresql/discovery_cache.sql
```

Importer le fichier précédemment généré :

```bash
sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
  exec -T postgres \
  psql -X -v ON_ERROR_STOP=1 -U pepeuch_ai -d pepeuch_ai \
  < /opt/pepeuch-ai/data/discovery-poc/local5.pg.sql
```

Sur SurrealDB 3.3 : valider le script, puis l'importer par `/import` (commande
`/surreal import`), **pas** en passant les statements `OPTION IMPORT` à `/sql` :

```bash
sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml \
  exec -T surrealdb /surreal validate /data/discovery-b2-local5.surql

sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml \
  exec -T surrealdb /surreal import \
  --endpoint http://127.0.0.1:8000 \
  --namespace pepeuch_ai --database poc \
  /data/discovery-b2-local5.surql
```

**Attention :** contrairement au `COPY` PostgreSQL transactionnel, l'import
SurrealDB `/import` est appliqué instruction par instruction. Après un échec,
ne pas supposer un rollback global ; corriger puis relancer le même fichier
dont les `UPSERT` possèdent des IDs déterministes. Les permissions d'accès
éventuelles utilisent la configuration déjà présente sur la VM.

Lire les compteurs sans effacer :

```bash
sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
  exec -T postgres psql -U pepeuch_ai -d pepeuch_ai \
  -c 'SELECT count(*) FROM poc.discovery_cache;'

printf 'SELECT count() AS total FROM discovery_cache GROUP ALL;\n' | \
  sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml \
  exec -T surrealdb /surreal sql \
  --endpoint http://127.0.0.1:8000 \
  --namespace pepeuch_ai --database poc --hide-welcome
```

Réimporter **le même snapshot** : le total doit rester à **5**, pas 10.

## C. Test facultatif des sources publiques externes

Après succès du POC local, recueillir des métadonnées publiques ciblées :

```bash
python3 database/poc/collect_discovery_snapshot.py \
  --models-limit 5 --include-online --agents-limit 3 \
  > /opt/pepeuch-ai/data/discovery-poc/with-online.json
```

Ce mode ne télécharge pas de modèles : il lit seulement 2 dépôts HF, un
catalogue d'agents épinglé dont **3** entrées uniques sont retenues et un NIM
public par `resourceId`+tag. Les 5 modèles locaux restent présents. Les deux
snapshots n'ont **pas le même scope** : une comparaison « suppressions » entre
eux serait trompeuse, et notre comparateur la refuse.

Pour comparer deux collectes avec scope identique :

```bash
python3 database/poc/compare_discovery_snapshots.py \
  /opt/pepeuch-ai/data/discovery-poc/old.json \
  /opt/pepeuch-ai/data/discovery-poc/new.json
```

## Points non résolus (hors B2)

- Aucun scheduler, aucun selector, aucun test d'inférence ou GPU.
- Pas de nettoyage automatique des entrées qui ne sont plus observées.
- Pas encore d'historique d'événements en base ; conserver les snapshots JSON
  avant d'ajouter des migrations ou politiques de rétention.
- Les données brutes suivent les limites et conditions de chaque fournisseur ;
  ne jamais stocker de jetons d'API dans les snapshots.
- PostgreSQL/SurrealDB ne sont **pas** encore départagés sur les performances,
  le graphe ou les vecteurs.
