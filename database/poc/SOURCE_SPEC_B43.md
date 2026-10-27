# Préparation B4.3 — interface déclarative du futur registre

Le prototype `source_spec_design.py` et ses huit tests de conception décrivent
les sept connecteurs après B4.2. **Il n'est relié à aucune CLI et n'exécute aucune
collecte.** Un registre orchestrant les sources reste un lot ultérieur.
Les 146 tests du dépôt POC passent, références B3.3 inchangées.

## SourceSpec proposé

| Champ | Sens | Ne doit pas servir à |
| --- | --- | --- |
| `source` | Namespace exact du connecteur existant | Renommer une source ou fusionner des noms similaires |
| `entity_types` | Familles de ressources autorisées dans ce contrat | Convertir automatiquement une offre en artefact ou agent |
| `selection_modes` | Formes de scope déjà observées dans B2/B3 | Promettre qu'un collecteur commun ou un batch existe déjà |
| `collection_strategy` | Description explicite de l'opération de métadonnées | Résoudre une fonction ou importer un plugin depuis une chaîne |
| `revision_kind` | Commit catalogue, SHA dépôt, tag mutable, ou aucune révision | Faire d'un tag/timestamp une preuve d'immuabilité |
| `revision_validation` | Niveau réel de validation actuel | Prétendre que HF vérifie un SHA complet alors que son normaliseur accepte une chaîne |
| `revision_nullable` | Absence admise dans les records | Inventer une révision à partir de la date d'observation |
| `access_scope` | Local épinglé, HTTP anonyme ou SDK géré par son environnement | Accorder des droits de téléchargement ou d'inférence |
| `transport` | Nature, hôtes configurés, limites et garanties réellement actives | Appliquer rétroactivement une allowlist au client B1 ou un timeout urllib au SDK |
| `capabilities` | Capacités de métadonnées testées | Affirmer une inférence, un téléchargement ou une capacité GPU opérationnels |

`SourceSpec` et `TransportSpec` sont des dataclasses gelées et convertissent
leurs collections en frozensets. `source_index` refuse les doublons et retourne
une vue non modifiable. `SOURCE_SPECS` est une table **statique de conception**,
sans moteur d'exécution, résolution de symboles, découverte de plugins ou import
d'adaptateur. Aucun ID B2 ni snapshot n'est calculé par ces descriptions.

Les hôtes `configured_hosts` décrivent le code actuel : seuls CSGHub/MoArk
appliquent la politique stricte B4.2. Pour B1, `strict_url_policy=false` et
`redirects=urllib_default`. Pour ModelScope, taille et timeout sont null, avec
`redirects=sdk_managed` et `access_scope=sdk_managed`. Cela évite de représenter
une intention future comme une garantie déjà obtenue.

## Les sept descriptions

| Source | Sélection | Révision / validation | Transport | Capacités propres de métadonnées |
| --- | --- | --- | --- | --- |
| models.dev | first_n_sorted | catalogue / SHA-1 exact issu du CLI | fichiers locaux | épinglage local |
| huggingface | exact_ids | dépôt / chaîne non vide si présente | HTTP B1, 3 Mo, timeout par défaut 20 s | liens de base déclarés, listing de fichiers, formats observés |
| awesome-ai-agents | first_n_unique | catalogue / SHA-1 exact | HTTP B1, 3 Mo, timeout par défaut 20 s | épinglage du catalogue |
| nvidia-nim-metadata | exact_tag | tag mutable / syntaxe de tag | HTTP B1, 3 Mo, timeout par défaut 20 s | profils de déploiement ; aucun GPU exécuté |
| modelscope | exact_ids | dépôt / SHA complet si disponible | SDK officiel, garanties réseau non imposées ici | métadonnées de dépôt uniquement |
| csghub | exact_ids | dépôt / SHA complet si disponible | HTTP borné, 2 Mo, 20 s, redirect interdit | listing de fichiers et formats observés ; agents exclus |
| moark | exact_ids après roster | aucune / null | HTTP borné, 2 Mo, 20 s, redirect interdit | listing d'offres servies ; aucune inférence ni poids validés |

Toutes les sources déclarent `metadata` et `offline_fixture` : cela signifie
que leurs normalisations peuvent être testées hors ligne, pas qu'une option
commune `--fixture` existe déjà. Les CLI actuelles et leurs limites restent
leur interface opérationnelle. Les limites B1 sont des valeurs par défaut,
le CLI existant autorisant son timeout propre dans l'intervalle documenté.

## Tests de conception

- La table contient exactement les sept namespaces/types/modes des snapshots
  figés en B4.0, sans type d'agent ajouté à CSGHub.
- Les différences SHA HF / SHA complets B3 / tag NIM / absence MoArk restent
  visibles, y compris les révisions optionnelles.
- Les capacités MoArk n'autorisent pas à annoncer une inférence opérationnelle.
- SDK et HTTP legacy ne peuvent pas annoncer les garanties du transport borné.
- Les descriptions, collections et index résistent aux mutations d'appelants ;
  namespaces/types/modes inconnus et doublons sont refusés explicitement.
- Un interpréteur neuf interdit l'import des SDK, adaptateurs et modules de
  collecte, ainsi que le réseau : importer le prototype réussit sans eux.

## Contrat à ajouter avant un registre opérationnel

1. **Sélection validée par source.** Prévoir une structure séparée pour les
   paramètres d'une exécution : IDs exacts, N, resourceId/tag, endpoint fixé,
   filtres et périmètre d'accès. Refuser les modes inconnus. Les règles d'ID
   restent dans chaque adaptateur ; le registre n'invente aucun ID canonique.
2. **Binding explicite.** Dans un module d'exécution séparé, relier les sept
   namespaces à des fonctions déjà testées, avec injection de transport/SDK.
   L'initialisation de la table ne doit ni appeler ni importer un SDK optionnel.
   Aucun chargement dynamique de code fournisseur à partir d'une entrée utilisateur.
3. **Résultat par source.** Distinguer succès/absent ciblé/échec/incomplet et
   snapshot validé. Ne pas fabriquer un scope réduit en masquant un échec. Les
   sources indépendantes doivent pouvoir produire un rapport exploitable sans
   supprimer ou écraser les observations antérieures.
4. **Manifeste hors payload.** Version du connecteur, nature de révision, preuve
   synthétique/réelle, paramètres de transport et diagnostic sans secrets doivent
   d'abord aller dans un rapport séparé, sans modifier les empreintes B2 importées.
   Le scope stable et l'état de tentative/cursor ne doivent pas être confondus.
5. **CLI manuelle opt-in.** Préserver les CLI actuelles jusqu'à équivalence des
   requêtes, scopes et snapshots démontrée. Le nouveau registre ne déclenche
   aucune collecte à l'import, à la découverte d'une source ou au démarrage.

L'exécution incrémentale, budgets, délais, Retry-After, reprise, checkpoints,
historique et rétention restent ultérieurs. Les générateurs PostgreSQL/SurrealDB
consomment toujours des snapshots et n'entrent pas dans SourceSpec. L'admission
au Personal Model Catalog demeure un workflow explicite distinct.

## Décisions nécessitant une revue de contrat

- Une ou plusieurs révisions NIM par ressource : conserver aujourd'hui
  `source_id=resourceId`, un tag par snapshot, sans changement silencieux de clé.
- Éventuels domaines/installations/comptes supplémentaires : ils ne figurent
  pas dans les clés actuelles. Définir leur namespace avant tout ajout.
- Convention commune synthétique/réel et périmètre authentifié : choisir une
  représentation versionnée ou un manifeste, sans jeton ou identité sensible.
- Différences accès/visibilité et sélection incomplète : conserver les sorties
  actuelles en attendant une décision, sans universaliser les règles métier.
- Politique B1 de redirection et contrôle du SDK : valider ces garanties avant
  migration et avant tout quota/retry commun.

Aucune de ces décisions n'a été prise de manière irréversible pendant B4.
La prochaine étape proposée est la revue du prototype, puis un premier binding
manuel sur fixtures, sans nouvelle collecte réseau ou modification de base.
