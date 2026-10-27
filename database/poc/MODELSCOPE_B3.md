# B3.1 — ModelScope metadata, contrat ciblé (27 octobre 2026)

**Portée :** un seul dépôt **modèle** de ModelScope, sans poids, sans accès
GPU, sans login ni écriture en base. Ce lot n'est pas un crawler du Hub.

L'API officielle est fournie par le SDK `modelscope-hub`, `HubApi.get_repo()`.
Le SDK unifie les requêtes OpenAPI et le repli legacy. Le résultat
`RepoInfo.to_dict()` est transformé en `SourceRecord` pour notre B2.

Références (documentation fournisseur) :

- https://github.com/modelscope/modelscope_hub
- https://github.com/modelscope/modelscope_hub/blob/main/src/modelscope_hub/api.py
- https://github.com/modelscope/modelscope_hub/blob/main/src/modelscope_hub/cli/repo.py

## Contrat et précautions

- `source = modelscope`, `entity_type = model_artifact`, identité `owner/name`.
- Les clés du Discovery Cache sont séparées de celles de Hugging Face et de
  CSGHub, même lorsque les noms se ressemblent. Aucune fusion automatique.
- La visibilité accepte `1=private`, `3=internal`, `5=public` ou les labels
  équivalents ; absence = `unknown`, distinct de `false`.
- `gated` et `private` sont indépendants : privé ne signifie pas automatiquement
  accès sur demande, et un `gated` explicitement vrai reste visible.
- Licence, tags, compteurs, description et date sont optionnels ; leur absence
  ne constitue pas une valeur négative.
- Un `last_modified`, une branche `master` ou un ID numérique interne ne sont
  **pas** des SHA Git. Seul un hash explicite complet est traité comme
  `source_revision`. Le SDK annonce que le paramètre `revision` de
  `HubApi.get_repo()` est actuellement réservé/ignoré.
- Aucune relation de parenté avec un modèle Hugging Face n'est inférée.
- L'adaptateur refuse les clés de type secret/token, les identités divergentes
  et les types de dépôt incorrects. `raw_metadata` reste JSON-compatible.
- Les métadonnées de ModelScope peuvent changer entre deux appels. La date
  d'observation et la révision explicite doivent rester distinctes.

## Essai local entièrement hors ligne

Depuis `/opt/pepeuch-ai/repo` :

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -v
mkdir -p /opt/pepeuch-ai/data/discovery-poc
python3 database/poc/probe_modelscope.py \
  --fixture database/poc/fixtures/modelscope_repoinfo.synthetic.json \
  > /opt/pepeuch-ai/data/discovery-poc/modelscope-SYNTHETIC-DO-NOT-IMPORT.json
```

La **réponse API de la fixture est synthétique** ; l'identifiant choisi est un
exemple public du SDK officiel, mais ses compteurs et sa licence sont inventés
pour les tests. **Ne jamais importer ce snapshot dans les bases**.

## Sonde réelle facultative avec le SDK officiel

Ne pas installer dans le Python système Debian. Si l'on souhaite tester le
réseau ensuite, utiliser un environnement virtuel isolé (version du SDK à
vérifier avant installation) :

```bash
python3 -m venv /opt/pepeuch-ai/data/discovery-poc/modelscope-venv
/opt/pepeuch-ai/data/discovery-poc/modelscope-venv/bin/python -m pip install 'modelscope-hub==0.4.0'

/opt/pepeuch-ai/data/discovery-poc/modelscope-venv/bin/python \
  database/poc/probe_modelscope.py --online \
  --model-id Qwen/Qwen3-0.6B \
  --endpoint https://modelscope.cn \
  > /opt/pepeuch-ai/data/discovery-poc/modelscope-live.json
```

`--online` n'appelle que `HubApi.get_repo()`, n'invoque aucune commande de
téléchargement, de création, d'upload ou de déploiement. Pas de clé requise
pour un dépôt public si le service accepte l'accès anonyme ; tout refus
réseau/authentification doit être signalé, pas contourné.

**Ne pas importer le snapshot réel avant :** (1) lecture des champs obtenus,
(2) validation du SHA et de l'identité, (3) contrôle de la licence/gating.
Si ModelScope renvoie un schéma inattendu, conserver le JSON source uniquement
dans le répertoire de travail hors Git, puis adapter les tests.

## Sources suivantes (non implémentées dans B3.1)

| Fournisseur | Ressource primaire | Distinction importante |
| --- | --- | --- |
| OpenCSG / CSGHub | `model_artifact` | Le dépôt Git-LFS et l'API Gateway d'inférence sont **deux** surfaces différentes ; `/v1/models` sur le gateway liste les modèles servis, pas les poids. |
| MoArk / OSChina | `inference_endpoint` | API de modèles servis et workflows ; un modèle disponible par API n'est pas une preuve de dépôt de poids téléchargeables. |

Les premiers contrats de ces sources devront également être testés en
lecture seule, avec clés propres à la source, champs manquants conservés, et
aucune assimilation automatique à des références Hugging Face.

Sources officielles :

- https://opencsg.com/docs/en/csghub/101/function/model/download_models
- https://opencsg.com/docs/en/csghub/101/function/aigateway/model_access
- https://moark.ai/docs/openapi/v1
