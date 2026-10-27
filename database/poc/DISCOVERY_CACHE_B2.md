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
| `modelscope` | `model_artifact` | [B3.1](MODELSCOPE_B3.md) : POC modèle ciblé validé sur la VM, imports et réimports PG/SurrealDB validés |
| `csghub` | `model_artifact` | [B3.2](CSGHUB_B3.md) : POC modèle ciblé validé sur la VM ; ressources `agent_resource` encore à étudier |
| `moark` | `inference_endpoint` | [B3.3](MOARK_B3.md) : POC validé sur la VM, 14 ressources par moteur après imports et réimports ; inférence non testée |

Les sept connecteurs de métadonnées sont disponibles pour les périmètres
ciblés décrits ici. Les validations B3.1, B3.2 et B3.3 sont des **POC manuels**,
avec sondes en lecture seule et imports explicites. Elles ne constituent pas
un Discovery Service automatisé : registre commun, exécution planifiée,
quotas, reprise et suivi incrémental restent à développer. Les connecteurs
B3 possèdent leurs propres sondes ; ils ne sont pas encore intégrés à l'option
`--include-online` du collecteur B2.

Clôture B3.3 sur Debian 13, le 27 octobre 2026 (résultats VM communiqués par
l'utilisateur) : **91 tests**, **14 ressources PostgreSQL et 14 SurrealDB**,
réimportation idempotente, **405 modèles historiques PostgreSQL préservés**.
Le catalogue public MoArk a été sondé ; **aucun accès réel à l'inférence n'a
été testé**. Le Discovery Cache reste distinct du Personal Model Catalog.

Références officielles des études B3 :

- ModelScope : https://github.com/modelscope/modelscope_hub
- OpenCSG / CSGHub : https://github.com/OpenCSGs/csghub et https://www.opencsg.com/docs/en/csghub/101/introduction
- MoArk : https://moark.ai/docs/

**Important** : le fait qu'une plateforme soit compatible Hugging Face ne
prouve pas qu'elle sert le même fichier ou la même révision. Pas de fusion
canonique sur la seule similitude des noms.

### Études B3 validées et extensions restantes

1. **ModelScope** : B3.1 a validé les métadonnées d'un dépôt modèle connu et
   leur import. Étendre l'échantillon et l'étude des révisions, licences,
   fichiers, restrictions d'accès et liens de parenté *explicites*.
   Les datasets, Studios, agents et MCP ne deviennent pas automatiquement des
   `model_artifact` : chaque famille réclame un contrat adapté.
2. **OpenCSG / CSGHub** : B3.2 a validé l'API officielle de métadonnées d'un
   dépôt modèle et son import. Les ressources d'agents et l'AI Gateway restent
   à étudier séparément ; conserver l'origine de chaque relation croisée,
   sans dédupliquer sur le nom.
3. **MoArk / OSChina** : B3.3 a qualifié le catalogue public Serverless,
   l'authentification documentée et l'import de son offre servie comme
   `inference_endpoint`. L'accès réel à l'inférence n'a pas été testé. Ne créer
   une fiche `model_artifact` que si un dépôt de poids et sa provenance sont
   prouvés ; la bibliothèque Git/LFS est une surface distincte.

Pour chaque extension de source : commencer par **une sonde ciblée en lecture seule** et
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
