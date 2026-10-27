# B4.2 — transport de métadonnées borné et injectable

**138 tests réussis**, dont 16 nouveaux cas transport/SDK. Aucun appel réseau
réel n'a été nécessaire. Ni retry, ni collecte planifiée, ni accès à une base.

## Interface HTTP

`metadata_http.py` expose :

- `HTTPPolicy(allowed_hosts, max_response_bytes, timeout_seconds)` : hôtes
  explicites figés, limite positive en octets et timeout fini de 0 à 60 secondes
  (borne basse exclusive). Aucun quota fournisseur n'est inventé par ce réglage.
- `MetadataTransport.fetch(request, *, timeout, max_bytes) -> HTTPResult` : point
  d'injection de transport ; contrat d'un seul GET sans redirection ni retry.
- `HTTPResult(status, body)` : statut numérique et octets ; aucune donnée de
  requête/authentification ajoutée aux snapshots.
- `get_metadata_json(url, *, policy, transport=None)` : validation avant réseau,
  lecture bornée, contrôle HTTP 200, JSON strict, racine objet et copie sûre.

Le transport urllib lit au maximum `max_bytes + 1`, ferme la réponse et permet
de détecter un dépassement. Le contrôle de taille est aussi appliqué aux résultats
des transports injectés. Les corps de statuts d'erreur/redirection ne sont pas lus.
Les erreurs urllib sont fermées sans conserver le corps distant.

URL autorisée : HTTPS, hôte exact dans la liste, port implicite/443, pas de
userinfo, fragment ou caractère de contrôle/espace. Les clés d'authentification
dans les query parameters sont refusées. Les headers sont Accept JSON et le
User-Agent POC ; pas de Cookie, Bearer ou POST. Une redirection est interdite
même vers un autre chemin/hôte autorisé : aucun suivi automatique.

L'allowlist de noms n'est pas un mécanisme de DNS pinning. Le timeout urllib
reste un délai de socket, **pas une deadline totale** contre un serveur envoyant
lentement des octets. Budget total, concurrence, proxy réseau et périmètres
authentifiés demandent des politiques explicites dans un lot ultérieur. Le
transport injectable est une dépendance de confiance : ne pas brancher un client
qui suit les redirects ou effectue ses propres retries en secret.

## Erreurs et sémantique fournisseur

| Erreur | Données exposées | Comportement |
| --- | --- | --- |
| URL/politique refusée | Message statique, sans URL ou valeur query | Arrêt avant transport |
| HTTP 3xx/401/403/404/429/500/503, etc. | `MetadataHTTPError`, sous-classe `HTTPError`, code conservé, URL/headers/corps distants exclus | Une tentative, aucun retry |
| Timeout direct ou enveloppé dans URLError | `MetadataTimeoutError` | Une tentative, message statique |
| Autre erreur réseau | `MetadataNetworkError` | Une tentative, sans raison distante |
| JSON/UTF-8 invalide, doublons, données non finies, racine incorrecte, clés de secrets, taille excessive | `MetadataResponseError` | Aucun payload partiel retourné |

`MetadataHTTPError` reste compatible avec `except HTTPError` et `.code`, afin
que la future migration NIM puisse conserver **404 = indisponible pour ce tag**.
Le client commun ne traduit jamais un 404 en suppression ni en modèle inexistant.
Un test passe cette erreur au chemin NIM existant ; les autres statuts remontent.
Un 304 est également refusé à ce stade : aucun cache conditionnel n'existe encore.

## Migrations effectuées et équivalence vérifiée

CSGHub et MoArk ont migré vers ce client. Leurs fonctions `read_online`, leurs
CLI, constantes et points d'injection de test restent disponibles. Les IDs sont
validés avant réseau ; endpoints, query, Accept, User-Agent, timeout 20 s et
limite 2 Mo sont conservés. Les tests HTTP historiques des deux sources restent
inchangés et réussissent.

Vérifications indépendantes supplémentaires, avec le code archivé de B3.3 :

- stdout JSON des CLI fixture ModelScope, CSGHub et MoArk identique hors
  `captured_at`, date d'observation volontairement variable ;
- génération PG et SurrealDB du snapshot synthétique des sept sources : **octets
  d'import identiques** à B3.3 ; génération uniquement, sans base contactée ;
- sept normalisations, clés, payloads, snapshots et comparaison partielle B4.0
  toujours identiques ; JSON de référence non modifié.

## Interface SDK ModelScope

`metadata_sdk.py` définit les Protocol `RepositoryClient` et `RepositoryInfo`,
ainsi que `read_model_repository(client, requested_id)`. Le helper appelle
uniquement `get_repo(..., repo_type="model").to_dict()`, une fois, puis vérifie
la racine. Aucun clone, téléchargement, liste de fichiers ou protocole HTTP SDK
n'est réimplémenté. La sonde ModelScope lui délègue cet appel existant.

L'import de `modelscope_hub.HubApi` reste dans `read_online` ; aucun SDK optionnel
chargé pour les fixtures ou à l'import du helper. Les conversions Enum/date et
les règles de source restent dans le normaliseur ModelScope. Les erreurs SDK
sont résumées sans contenu. Le helper n'impose ni anonymat ni timeout au SDK :
ne pas déduire ces garanties d'une `HTTPPolicy` prévue pour urllib.

## Plan de migration restant

1. B1 HF/agents/NIM utilise encore son client `get_json` à 3 Mo. Sa politique
   urllib suit actuellement les redirections : la remplacer silencieusement par
   un refus strict ne serait pas une équivalence démontrée. Définir la politique
   de redirect et vérifier les routes/filtres avant migration, sans réseau en CI.
2. Conserver les limites/headers B1 et ses quatre hôtes propres (HF, API GitHub,
   raw GitHub, NGC), ainsi que la résolution puis lecture du commit agents.
3. Prouver l'équivalence de NIM 404 et de tous les scopes B2 avec les fixtures,
   puis effectuer une sonde réelle ciblée uniquement dans une étape explicitement
   activée. Aucune sonde réelle n'a été exécutée pendant B4.
4. Étudier séparément les limites/retries/configuration de credentials du SDK
   ModelScope avant de prétendre à un budget uniforme. L'interface actuelle
   prépare l'injection ; elle ne masque pas cette différence.

Les problèmes de compte/domaine, JSON d'observation synthétique/réel, granularité
des révisions et sélection partielle restent des décisions de contrat/registre,
pas des règles du transport HTTP.

Complément B4.3 : la lecture interrompue est testée pendant `response.read()`.
`IncompleteRead` est normalisé en erreur réseau sûre ; timeout et connexion coupée
conservent leur classement. Le stream est fermé sans décodage du corps partiel,
sans retry. Voir [DISCOVERY_B43.md](DISCOVERY_B43.md).

B4.4 ajoute seulement un carrier Retry-After validé et non sensible aux erreurs :
le client conserve son GET unique et ses headers d'erreur vides. Les reprises
sont exclusivement dans `discovery_execution.py`, sans appel implicite depuis
les CLI historiques ; voir [EXECUTION_B44.md](EXECUTION_B44.md).
