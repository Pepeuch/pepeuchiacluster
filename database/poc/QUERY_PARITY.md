# Phase 2 — POC PostgreSQL vs SurrealDB : parité des requêtes

Ce lot lance 14 paires de requêtes **en lecture seule** sur le même snapshot
models.dev (405 fiches, SHA 5e9fdbc3d88cb831627a93dc1362cc10773c176c).

Les deux bases doivent déjà fonctionner dans leurs réseaux Docker internes.
Ce script ne publie aucun port, n'ajoute aucun index, ne modifie aucune donnée
et n'utilise ni GPU ni identifiants transmis en ligne de commande.

## Sur la VM 150

Depuis le dépôt /opt/pepeuch-ai/repo :

    python3 -m unittest discover -s database/poc -p 'test_*.py' -v

    sudo python3 database/poc/benchmark_readonly.py

Pour produire un rapport JSON facultatif dans le dossier de logs :

    sudo python3 database/poc/benchmark_readonly.py --json-report /opt/pepeuch-ai/logs/db-query-parity-20261027.json

La génération refuse d'écraser un rapport qui existe déjà.

## Ce que teste le script

- Six totaux déjà validés individuellement (405, 196, 397, 8, 154, 135).
- Comptage des modèles avec outils et famille Qwen.
- Régression GPT-4.1 : source top-level tool_call=true et capacité normalisée
  tools_supported=true. Ceci distingue la parité entre moteurs de la justesse
  d'interprétation des métadonnées d'origine.
- Filtre combiné open weights + contexte.
- Recherche dans les métadonnées JSON imbriquées.
- Recherche ciblée par model_id et tri déterministe sur cinq IDs.

Une discordance de réponse, de typage JSON ou de syntaxe arrête le contrôle
et doit être analysée. Il ne faut pas « corriger » un moteur pour lui faire
afficher artificiellement la même valeur.

## Limite méthodologique importante

Le script enregistre des temps bruts CLI en millisecondes uniquement pour
diagnostiquer la chaîne de bout en bout. Ils incluent le lancement de Docker
exec et des clients psql/SurrealDB : **ils ne mesurent PAS le temps d'exécution
interne des moteurs** et ne permettent pas de les départager.

Avant toute conclusion de performance, prévoir un deuxième lot avec connexions
persistantes, index équivalents, plusieurs passes chaudes/froides, mesure p50/p95,
consommation mémoire réelle et plans PostgreSQL EXPLAIN ANALYZE / SurrealDB
EXPLAIN FULL.

Le snapshot actuel ne contient pas encore le schéma relationnel complet des
variantes, rôles, runtimes, matériels ou embeddings. Les tests de graphe et
de recherche vectorielle resteront donc ouverts.
