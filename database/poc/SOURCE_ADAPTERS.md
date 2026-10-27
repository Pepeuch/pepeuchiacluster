# Lots B1 et B1.1 — contrats de sources externes (lecture seule)

Ce lot vient après la parité 14/14 PostgreSQL/SurrealDB. Il ne modifie **aucune**
base de données et n'installe ni runtime ni pilote GPU.

## Contrats testés

| Source | Type logique | Identité | Révision | Relations explicites |
| --- | --- | --- | --- | --- |
| Hugging Face | `model_artifact` | `id` du dépôt modèle | `sha` Git du dépôt | `cardData.base_model` → autres IDs HF |
| Awesome AI Agents | `agent_resource` | `agents[].id` | commit Git du catalogue JSON | aucune relation de modèle inférée |
| NVIDIA NIM Metadata API | `nim_microservice` | `resourceId` du conteneur | `tag` du conteneur (non immuable) | aucune identité de modèle inférée |

Le contrat `SourceRecord` contient `source`, `source_id`, `source_revision`,
`entity_type`, `display_name`, `attributes`, `relationships`, `raw_metadata`.
`raw_metadata` reste disponible pour l'audit et le débogage ; son format n'est
**pas** un schéma de base de données définitif.

Règles :

- Une variante GGUF et le dépôt du modèle original sont **deux enregistrements**.
  Le lien `declared_base_model` n'existe que lorsque la source le déclare.
- `gated=false` signifie public ; `gated=manual` signifie approbation manuelle.
  L'absence de champ donne `unknown`, jamais `public`.
- `base_model` accepte une chaîne **ou** une liste ; une architecture absente
  reste `null`. Les formats sont des **indices positifs**, pas une preuve
  d'incompatibilité des formats non listés.
- Les ressources de `awesome-ai-agents` ne sont jamais insérées comme des modèles.
  Leurs étoiles GitHub ne sont pas des mesures de capacité ou de sécurité.
- Un même ID apparaissant plusieurs fois avec un contenu **strictement égal**
  est dédupliqué et comptabilisé. Deux contenus différents pour un même ID
  provoquent un échec ; aucune version n'est choisie arbitrairement.
- En cas de type inconnu, le normaliseur échoue avec une erreur explicite ;
  il ne convertit pas silencieusement des valeurs incompatibles.
- Les révisions des dépôts modèles et du catalogue d'agents restent distinctes.
  Ne jamais supposer qu'un nom similaire désigne le même modèle canonique.
- Les profils NVIDIA sont des spécifications **de microservice** ; ils ne prouvent
  ni l'identité d'un modèle Hugging Face, ni les droits NGC, ni le fonctionnement
  sur un GPU réel. Leur présence ne constitue pas une recommandation d'installation.

Pour le contrat NVIDIA, l'évaluation prudente de la RTX A2000 12 Go et les
résultats réels sont détaillés dans [NVIDIA_NIM.md](NVIDIA_NIM.md).

## Validation hors ligne (sans dépendance supplémentaire)

Depuis la racine du dépôt :

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -v
```

Les 9 tests B1 reproduisent le contraste Gemma/GGUF réellement observé
le 27 octobre 2026 et des entrées types du JSON Awesome AI Agents. Ce sont des
**fixtures minimales**, pas des copies complètes des réponses API.

Le 27 octobre 2026, l'audit public d'`awesome-agents.json` a montré 305 lignes
mais seulement **304 IDs uniques** : `open-interpreter-e4e017f4` est présent
deux fois avec un contenu identique. Ce cas réel est explicitement testé.

## Sonde réseau (facultative et sans authentification)

```bash
python3 database/poc/probe_source_adapters.py

# Un seul endpoint NVIDIA officiel, sans les deux autres sources :
python3 database/poc/probe_source_adapters.py --nim-only

# Contrats des trois sources dans un rapport :
python3 database/poc/probe_source_adapters.py --include-nim
```

Elle effectue seulement :

1. Deux lectures de métadonnées `/api/models/...` Hugging Face.
2. Une lecture GitHub pour résoudre le commit de `main` d'Awesome AI Agents.
3. Une lecture du JSON **à ce commit précis** et validation des IDs uniques.

Chaque réponse est limitée à 3 Mo ; timeout de 20 secondes par défaut.
La sortie présente un rapport réduit et la provenance, sans télécharger de
poids, lancer d'inférence, écrire des fichiers ou modifier les POC Docker.

La requête NVIDIA lit les métadonnées publiques d'un `resourceId` et d'un tag
précis ; un HTTP 404 signifie **métadonnées absentes pour ce tag**, pas
microservice inexistant. Elle ne requiert pas de clé NGC. Le rapport ne contient
pas les métadonnées intégrales, seulement des comptes et les contraintes
connues pour l'A2000. Une clé reste potentiellement nécessaire pour télécharger
le conteneur suivant ses droits de distribution.

Cette sonde est un test de contrat : elle ne mesure ni la performance des
bases, ni la disponibilité effective d'un modèle, ni sa compatibilité GPU.
Les valeurs rencontrées en ligne peuvent évoluer ; conserver les SHA rend les
observations vérifiables.

## Suite (hors de ce lot)

1. Étudier séparément les droits NGC/download, sans secrets dans Git ni dans
   les rapports ; aucun accès protégé n'a été testé par B1.1.
2. Concevoir un stockage idempotent `Discovery Cache`, distinct du catalogue
   personnel et du domaine `agent_resource`.
3. Relier les modèles uniquement par identifiants et provenance prouvée.
4. Tester l'import d'un même contrat dans PostgreSQL et SurrealDB, puis
   seulement ensuite les requêtes de graphe, vectorielles et les performances.
