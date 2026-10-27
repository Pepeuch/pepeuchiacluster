# B4.4 — budgets, erreurs et reprises contrôlées

Point de départ : B4.3 publié `bd888c4`, branche
`feat/discovery-b4-consolidation`, arbre initial propre, **167 tests réussis**.
Résultat : **229 tests réussis**, dont les 167 précédents sans modification.
Aucune collecte fournisseur, attente réelle, inférence, poids, GPU, base,
migration ou checkpoint persistant exécuté. La publication requiert une revue
explicite ; le SHA et son état de publication sont consignés dans le bilan de clôture.

La CLI commune reste limitée aux fixtures. Le nouveau moteur est une API Python
séparée, avec opérations et runtime injectés ; aucun transport réel, horloge,
sleep système, scheduler ou quota fournisseur n'est construit par défaut.

## Modules et frontières

| Module | Rôle | Ce qui reste hors périmètre |
| --- | --- | --- |
| `execution_models.py` | ResourceRef, politiques validées, tâches, résultats, rapports sûrs | Aucune identité B2 calculée ou modifiée par la politique |
| `discovery_execution.py` | Exécution séquentielle, comptage, classification et reprises explicites | Aucune liaison online avec les CLI ou sources |
| `retry_after.py` | Information normalisée : secondes, date UTC ou calendrier RFC850 | Aucun header brut stocké, aucun délai effectivement attendu |
| `metadata_http.py` | Toujours **un seul GET** ; transmet seulement Retry-After validé | Aucun retry implicite, aucun autre header/corps d'erreur réexposé |
| `synthetic_output.py` | Enveloppe synthétique optionnelle refusée par les importeurs B2 existants | Ni preuve cryptographique d'origine ni migration des imports historiques |

## Politique explicite

`ExecutionPolicy` ne possède aucun quota par défaut : tous ses paramètres sont
choisis par l'appelant, sans lien avec des limites officielles de fournisseurs.

| Paramètre | Garantie |
| --- | --- |
| `max_requests` | Nombre de dispatches `AttemptContext.request()` cumulés sur toutes les tentatives ; entier non négatif, 0 autorisé pour du travail local |
| `max_attempts` | Nombre maximal d'appels à l'opération d'une source ; entier strictement positif |
| `total_seconds` | Budget monotone total par source, incluant opération, normalisation/validation et attentes ; fini et strictement positif |
| `max_delay_seconds` | Plafond fini non négatif entre tentatives ; Retry-After n'est jamais raccourci pour tenir dans ce plafond |
| `backoff_seconds` | Base non négative, au plus égale au plafond ; progression exponentielle saturante |
| `resources` | Allowlist explicite de ResourceRef(source, source_id), sans fusion de namespace |
| `retry_http_statuses` | Sous-ensemble choisi de 429/500/502/503/504 ; 401/403/404/304 ne sont pas configurables comme retryables |
| `retry_transport_errors` | Choix explicite concernant timeout et connexion interrompue |

Les valeurs infinies, NaN, booléens déguisés en compteurs, limites négatives,
ressources absentes et codes permanents sont refusés. Ces validations sont
techniques, pas des quotas fournisseur. Les identifiants d'exécution sont des IDs
publics ASCII bornés ; URLs, query strings et nouvelles notions de compte ne sont
pas acceptées comme identifiants. L'élargissement de ce vocabulaire relève d'une
revue de contrat, sans changement des anciennes clés B2.

Une `SourceTask` associe une sélection B2 existante, les ressources planifiées,
une politique, une opération, un booléen `idempotent` et un booléen `synthetic`
explicites. Les sélections sont copiées et filtrées suivant le vocabulaire de
leur source : IDs, limite, resourceId/tag et endpoints officiels fixes. Aucun
champ libre de credentials, cookie, URL sensible ou compte n'entre dans un rapport.
La provenance synthétique/réelle est une déclaration de l'appelant, pas une preuve
d'authenticité du contenu. MoArk exige aussi la cohérence avec son scope existant.

## Runtime et comptage des requêtes

`ExecutionRuntime` exige quatre dépendances : `monotonic`, `wall_time`, `sleep`
et `jitter`. Les tests utilisent uniquement des fonctions simulées. L'horloge
monotone gouverne les budgets ; l'horloge UTC ne sert qu'à interpréter une date
Retry-After. Aucun appel à `time.sleep()` ou `time.monotonic()` n'est caché dans
le moteur.

Une opération reçoit un `AttemptContext`. Chaque requête contrôlée passe par
`context.request(resource, callback)` ; le callback reçoit le temps restant et
doit limiter son propre timeout, par exemple `min(timeout_socket, remaining)`.
Une tentative peut déclencher plusieurs requêtes, toutes décomptées, ou aucune
pour un traitement local. Un contexte fermé ne peut plus émettre de requête.

Le budget est **coopératif** : contrôles avant/après dispatch, après opération et
validation, avant/après attente. Un callback bloquant ne peut pas être préempté ;
un dépassement constaté interdit de publier son snapshot, même autrement valide.
L'elapsed n'est pas artificiellement plafonné et le manifeste signale l'overrun.
Les coûts de sérialisation finale du rapport ne sont pas une deadline temps réel.
Si l'horloge est invalide ou recule, l'exécution échoue avec la dernière mesure
valide disponible ; aucun résultat positif n'est fabriqué.

Les callbacks sont du code de confiance, pas des plugins sandboxés. Le moteur
compte les dispatches qui passent par le contexte : il ne peut pas compter des
requêtes cachées dans un SDK opaque ni empêcher un callback de contourner cette
interface. Aucune liaison SDK réelle n'est activée. Le futur contrat de transport
SDK devra résoudre ce point avant de promettre un budget de requêtes physiques.

Les budgets sont indépendants **par source et sélection**. Une exécution
séquentielle de plusieurs sources a des bornes correspondant à leurs politiques
respectives ; aucun budget global de lot ou de concurrence par hôte n'est prétendu.

## Classification et décisions de reprise

| Signal | Raison normalisée | Décision |
| --- | --- | --- |
| HTTP 401 / 403 | authentication_refused / access_forbidden | Échec terminal, aucune reprise |
| HTTP 404 | target_unavailable | Échec ciblé terminal, jamais une suppression |
| NIM HTTP 404 | metadata_unavailable_for_tag | Métadonnées absentes pour ce tag, pas disparition du service |
| HTTP 429 | temporary_quota | Reprise seulement si code autorisé et opération déclarée idempotente |
| HTTP 500/502/503/504 | temporary_provider_error | Même condition, choix des codes explicite |
| Timeout / connexion interrompue | timeout / connection_interrupted | Seulement si politique transport et idempotence l'autorisent |
| JSON, UTF-8, framing ou réponse invalide | invalid_json_or_response | Pas de retry |
| Erreur métier/contrat, ID incohérent, sélection interdite | invalid_schema / identity_mismatch / selection_forbidden | Pas de retry ; aucun examen de texte d'exception pour deviner une catégorie |
| HTTP 304 | validated_cache_required | Échec : B4.4 n'a aucun cache validé, donc jamais unchanged |
| Limite requêtes/tentatives/temps | raisons budget distinctes | Deferred ; aucun snapshot |
| Exception imprévue ou SDK opaque | unexpected_error | Échec terminal sûr, autres sources poursuivies |

Les erreurs typées `ExecutionError(Reason)` permettent à une opération d'indiquer
une identité incohérente sans inclure de données sensibles. Une ValueError métier
non typée reste invalid_schema et n'est jamais réessayée. Le moteur ne formate ni
`str(exc)` ni `repr(exc)` ; corps et URLs d'erreur ne sont pas conservés dans les
résultats. Un HTTPError de compatibilité explicitement injecté est normalisé à
l'entrée : statut et seul Retry-After filtré, sans conserver les autres headers.

## Backoff et Retry-After

Le délai local est `base * 2^(tentative-1)`, saturé sans calcul de puissance
gigantesque. `jitter(base)` renvoie un supplément non négatif et fini ; la somme
est plafonnée à `max_delay_seconds`. Une valeur invalide fait échouer le runtime.
Le délai effectif est le maximum entre ce délai local et le minimum du serveur.

Le transport ne transmet que `RetryAfter` validé : secondes entières, timestamp
UTC, composantes numériques d'une date RFC850 ou marqueur de valeur excessive.
Il accepte les trois formes HTTP-date et résout l'année RFC850 à deux chiffres
avec l'horloge UTC injectée et la règle des 50 ans, sans utiliser l'heuristique
fixe de siècle du parseur de mail. Les chaînes originales ne sont pas conservées.
Références normatives : [Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
et [HTTP-date](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.7).

Champ absent/invalide : backoff local. Date passée : minimum serveur zéro. Une
valeur numérique au-delà de la représentation retenue est marquée excessive et
reportée, jamais ignorée pour recommencer trop tôt. Une date lointaine valide ou
un délai égal/supérieur au budget restant produit deferred sans attendre. Un délai
serveur supérieur au plafond est reporté, sans troncature. Un réveil prématuré
arrête la reprise ; une attente échouée ou trop longue conserve les mesures
effectivement consommées et ne déclenche pas de nouvelle requête.

`MetadataHTTPError(status)` et `HTTPResult(status, body)` restent utilisables avec
leurs appels historiques ; seul un champ normalisé optionnel a été ajouté. Les
headers publics d'erreur restent `{}` et l'URL/corps distants restent exclus.
Le transport conserve une tentative unique ; aucune CLI historique ne reçoit une
politique de retry implicite.

## Résultats indépendants et manifeste

Une opération doit renvoyer `SourceObservation(snapshot, complete)`.
Un résultat positif exige un snapshot B2 intègre, le **même scope**, le bon
namespace/type et toutes les ressources explicitement planifiées, sans ajout
d'identité étrangère. NIM vérifie aussi le tag sélectionné. Les manques, un drapeau
complete faux, un scope réduit ou un payload corrompu ne produisent aucun snapshot.
« Complet » porte sur la sélection planifiée, pas sur la totalité du catalogue
fournisseur. Une découverte dynamique/paginée nécessitera un contrat ultérieur.

`SourceResult` peut représenter success, unchanged, deferred ou failed. Unchanged
est réservé dans la structure pour un futur cache ; le moteur B4.4 ne l'émet
jamais. Deferred/failed impose `snapshot=None`, sans faux snapshot vide. Une
erreur transitoire dont les reprises sont impossibles dans le budget est deferred ;
une erreur permanente ou une opération non idempotente est failed.

`execute_sources()` demande une tâche par source et retourne `ExecutionReport`.
Le lot entier est copié et revalidé avant la première opération pour isoler les
sélections des mutations ultérieures de l'appelant. Une configuration invalide
échoue avant toute source ; les erreurs opérationnelles restent indépendantes.
Les succès indépendants restent accessibles par `successful_snapshots()` ; aucun
snapshot B2 agrégé à scope réduit n'est fabriqué. Le manifeste expose :

- format `pepeuch-ai.discovery-execution/v1`, sources demandées et complétude du lot ;
- sélection et ressources publiques planifiées, statut, provenance déclarée ;
- tentatives, requêtes et temps consommés, limites configurées et overrun éventuel ;
- raison normalisée, dernière erreur normalisée et ID du snapshot validé éventuel.

Il ne contient ni brut fournisseur, headers, credentials, chemin système, exception
ou snapshot intégré. L'indication data_kind vaut synthetic/real/mixed et chaque
résultat garde son propre booléen synthetic. Les résultats positifs sont recopiés
et revalidés avant d'exposer leur ID ; les copies retournées ne mutent pas la
référence détenue. Le champ Python `snapshot` reste mutable : une mutation directe
est détectée par la revalidation avant publication d'un manifeste. Ces manifestes
ne changent aucune clé ou empreinte B2 et ne sont
pas des checkpoints persistants.

## Protection synthétique : mécanisme explicite et limite restante

La CLI B4.3 reste sans mode online. Une nouvelle option, sans changer son défaut,
produit une enveloppe à format distinct :

```bash
python3 database/poc/discover_sources.py --fixtures --protected-output \
  > /tmp/discovery-B44-SYNTHETIC-PROTECTED.json
```

`pepeuch-ai.synthetic-discovery/v1` contient `synthetic=true`,
`importable_as_real_observation=false` et le snapshot B2 intact sous `snapshot`.
Les deux générateurs d'import existants refusent le format extérieur **avant la
première instruction SQL**, sans modification de leur contrat. Aucun déballage
automatique n'est fourni. Le mode brut historique et ses références restent
compatibles.

Cette protection est volontairement **optionnelle et non universelle**. Une
copie B2 brute historique ne permet pas de prouver son origine synthétique ;
l'utilisateur peut aussi déballer volontairement une enveloppe. Les snapshots
retournés en mémoire ne doivent donc pas être importés automatiquement en fonction
de leur seul format valide. Les tests démontrent le rejet de l'enveloppe, pas une
authenticité cryptographique ni le blocage de tout import historique brut.

Options à examiner avant toute protection obligatoire :

1. Enveloppe par défaut de la CLI fixtures, avec option explicite pour l'ancien
   stdout B2 : changerait la forme de sortie par défaut, donc pas appliqué ici.
2. Manifeste de provenance obligatoire lié au snapshot pour les importeurs, avec
   chemin legacy explicite et décisions pour les observations B2/B3 existantes :
   évolution du contrat d'import et de la confiance, pas appliquée ici.
3. Nouveau format versionné d'observation : préciser les champs hors identité et
   la validation de provenance ; ne pas ajouter silencieusement un marqueur dans
   les payloads/scopes historiques, ce qui changerait leurs empreintes.

## Validation et suite B4.5

Les 62 nouveaux tests complètent les 167 existants : 48 exécution, 8 Retry-After
et transport, 6 protection. Ils couvrent les 16 scénarios de la mission, les trois
formats de dates, le siècle RFC850, les valeurs extrêmes, budgets distincts,
timeouts ajustés au temps restant, sélection partielle, source indépendante,
mutation d'un plan, contexte fermé, réveil prématuré, erreurs sensibles et enveloppe
rejetée par les deux moteurs de génération sans base contactée.

Les sept snapshots B3.3 et leurs empreintes restent inchangés ; le JSON de
référence n'a pas été réécrit. La CLI brute conserve le snapshot agrégé
`s_e1ea910f305c35e27a63aa1a911c028ac5c0a4c2ca98b46ff5c66e9674ee5a60`.
`git diff --check` est propre. Tous les tests de cette étape sont hors ligne,
avec attentes simulées ; aucune politique fournisseur n'a été mesurée ou supposée.

Décisions B4.5 : provenance obligatoire et compatibilité d'import ; cache validé
lié au scope exact avant de traiter 304 ; atomicité/rétention des checkpoints et
reprise après arrêt ; granularité des budgets et SDK ; curseurs/complétude des
sélections dynamiques ; concurrence/rate limits par hôte et éventuel budget global
de lot. Ces décisions ne sont pas anticipées par une persistance ou un scheduler.
