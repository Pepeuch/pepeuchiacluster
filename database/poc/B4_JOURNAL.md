# Journal B4 — consolidation du Discovery Cache

Branche de travail : `feat/discovery-b4-consolidation`.
Départ : B3.3 `d528580ddd6e1c4b364b64e2322eb2649e7b2e62`.
Autorisation : mission autonome, commits locaux par lot validé ; aucun push.
Les fichiers B4.0 déjà en cours ont été conservés lors de la création de branche.
Aucune modification préexistante sans rapport n'a été déplacée ou effacée.

## B4.0 — caractérisation (27 octobre 2026)

- Étude des sept contrats, de leurs sondes, tests et du bilan architectural fourni.
- Référence isolée par `git archive` du commit publié ; **91/91 tests initiaux**.
- Ajouts : `CONTRACTS_B40.md`, `test_contract_reference_b40.py`,
  `fixtures/contracts_b40/{inputs.synthetic.json,reference.b33.json,models/example/*.toml}`.
  Réutilisation des trois fixtures B3 existantes ; aucun adaptateur modifié.
- Références littérales de normalisation, clés, payloads, scopes et snapshots ;
  17 tests nouveaux, y compris NIM multitag, inconnues, liens, absence sans
  suppression, opérations sans mutation et aliasing mémoire historique.
- Le premier passage sur les tests en construction a signalé le JSON de référence
  manquant ; la capture B3.3 a ensuite été réalisée et les 17 tests ont réussi.
- Décisions : ne pas corriger accès/visibilité, identité NIM, scopes ou révisions
  dans B4.0. L'aliasing est constaté explicitement, sans prétendre à une immutabilité
  que le code actuel ne garantit pas. Une copie défensive B4.1 doit préserver
  les octets sémantiques des snapshots de référence.
- Validation complète et résultats : **108 tests**, références B3.3 identiques ;
  `git diff --check` propre. Aucun réseau, poids, inférence, GPU ou base contactés.

## B4.1 — primitives communes (27 octobre 2026)

- Ajout de `metadata_primitives.py` et de 14 tests ; documentation
  `PRIMITIVES_B41.md`. Extraction des validations de types réellement identiques
  et des copies JSON B3, avec wrappers/signatures maintenus.
- Copie défensive dans SourceRecord et lors de la création des payloads/scopes
  B2 ; protection récursive de credentials dans les sept contrats. Le callback
  Enum/date de ModelScope est préservé et son résultat contrôlé.
- Parseur strict pour les CLI JSON B2 et les sondes B1/B3 : doublons, syntaxe,
  UTF-8 et valeurs non finies refusés. Résumés d'erreurs sans valeurs sensibles.
  Les CLI restent utilisables avec les mêmes arguments et sorties valides.
- Les tests d'aliasing B4.0 ont d'abord échoué comme attendu après la copie ;
  deux tests ont été adaptés à la garantie B4.1, sans retoucher la capture B3.3.
  SHA256 du JSON de référence toujours
  `ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
- Résultat : **122 tests réussis**, toutes les sorties B3.3 figées identiques,
  `git diff --check` propre. Aucun transport réel, accès base ou schéma modifié.
- Décision : durcir les entrées dangereuses/ambiguës, sans universaliser les
  règles métier. La détection par clés ne promet pas d'identifier des secrets
  arbitraires dans du texte libre. Accès, domaines/comptes et NIM restent ouverts.

## B4.2 — transport commun (27 octobre 2026)

- Ajouts : `metadata_http.py`, `metadata_sdk.py`, `test_metadata_http.py` et
  `TRANSPORT_B42.md`. Politiques explicites, transport injectable, un GET borné,
  refus de redirect/auth dans URL, parsing strict, erreurs nettoyées sans retry.
- Migration des seules sondes CSGHub et MoArk dont les contraintes communes
  ont une équivalence testée ; les 29 tests historiques de ces sources restent
  inchangés. ModelScope délègue son unique appel SDK à l'interface injectable ;
  son import optionnel reste tardif. B1 conserve son transport historique.
- 16 nouveaux tests : succès, syntaxe/ambiguïté/secret JSON, limite exacte et
  dépassement, timeout direct/enveloppé, redirect, 401/403/404/429/500/503,
  absence de retry, URL refusée avant I/O, fermeture et SDK simulé.
- Un test supposait que HTTPError(fp=None) ne crée pas de stream ; urllib crée
  un buffer vide. L'attendu a été précisé : aucun octet de corps distant conservé,
  tout en préservant la compatibilité HTTPError. Pas de changement métier associé.
- **138 tests réussis**, `git diff --check` propre. Comparaison indépendante aux
  CLI B3.3 archivées : trois sorties fixture identiques hors date d'observation ;
  les deux imports générés sont identiques octet pour octet. Références B4.0 intactes.
- Limites documentées : timeout socket ≠ deadline totale ; allowlist ≠ DNS pinning ;
  SDK non soumis au transport urllib ; migration B1 différée car sa politique de
  redirect actuelle diffère. Aucun endpoint réel interrogé et aucune base ouverte.

## Préparation B4.3 — SourceSpec (27 octobre 2026)

- Ajouts : `source_spec_design.py`, `test_source_spec_design.py`,
  `SOURCE_SPEC_B43.md`. Prototype de dataclasses et table statique des sept sources,
  sans collecteur, plugin, génération d'identité B2 ou liaison aux CLI.
- Huit tests de conception : conformité aux namespaces/types/scopes B4.0,
  nature/validation des révisions, absence de promesse d'inférence, limitations
  SDK/B1 explicites, index/collections gelés et imports inertes en interpréteur neuf.
- Le prototype ne prétend pas que B1 applique une allowlist, que les SDK ont un
  timeout commun ou que le type inference_endpoint est une preuve d'accès réel.
- **146 tests réussis**, références B3.3 inchangées et `git diff --check` propre.
  Aucun SDK optionnel chargé par le prototype, aucun réseau et aucune base ouverts.
- Décisions différées : multitag NIM, isolation domaines/comptes, convention
  synthétique/réel, accès/visibilité, succès partiels, redirects B1 et garanties SDK.
  Le futur binding collecteur/registre doit faire l'objet d'une revue séparée.

## Revue finale de la session initiale

- Les 11 fichiers de tests historiques (91 cas) sont identiques au commit B3.3.
  Les signatures des fonctions publiques et les déclarations d'options CLI
  existantes ont été comparées par AST : aucune modification.
- Références littérales et SHA256 du JSON B4.0 inchangés. Les seules évolutions
  intentionnelles sont les copies défensives, le rejet d'entrées dangereuses ou
  ambiguës et les diagnostics plus sûrs ; aucun changement de payload valide.
- Scan ciblé de motifs de credentials et revue des sentinelles de tests : aucun
  vrai secret détecté. Les données d'authentification des tests sont explicitement
  synthétiques, sans jeton utilisable.
- Suite complète finale en mode verbose : **146/146 tests réussis** ;
  `git diff --check` propre. Commits locaux séparés par lot ; aucun push.
- Aucune requête fournisseur, inférence, GPU, base, migration ou planification
  exécutée. La branche B3.3 de référence et `main` ne sont pas modifiées.

## B4.3 — liaisons et CLI commune sur fixtures (27 octobre 2026)

- Point de départ propre : `6483cb9`, branche `feat/discovery-b4-consolidation`.
  Travail limité aux sept demandes suivantes : lecture HTTP interrompue, liaisons
  SourceSpec, CLI commune manuelle, fixtures seulement, comparaison B3.3, CLI
  historiques préservées et aucun réseau réel/import en base.
- Ajouts : `discovery_registry.py`, `discover_sources.py`,
  `fixtures/discovery_b43.synthetic.json`, `test_discovery_registry.py` et
  `DISCOVERY_B43.md`. Mise à jour de TODO et des documents SourceSpec/transport.
- Les liaisons sont explicites, immuables et tardives, sans résolution de module
  depuis la configuration. Sept normaliseurs existants, aucun nouveau client
  online ni SDK importé pour normaliser les fixtures.
- Le manifeste sépare chemins locaux, scope et révisions de catalogue ; lectures
  JSON bornées/strictes, provenance synthétique obligatoire, contrôle des modes,
  identités et types contre SourceSpec. Paths hors répertoire et symlinks sont
  refusés, y compris dans l'arbre TOML ; aucun import ou fichier de base généré.
- `--fixtures` et `--list-sources` sont explicites et mutuellement exclusifs ;
  `--source` répétable et date d'observation modifiable. Pas d'exécution implicite
  ou de mode online. Le JSON est validé avant stdout ; une erreur tardive ne
  publie aucun résultat partiel. Diagnostic synthétique sur stderr seulement.
- Le premier test a confirmé qu'IncompleteRead n'était pas normalisé. Le client
  le traite maintenant comme erreur réseau sans corps, fermeture du stream et
  aucun retry. Un second test reproduit avec HTTPResponse en mémoire la lecture
  courte sans exception : Content-Length est maintenant vérifié et borné.
- Ajout de trois tests transport (dont coupure/timeout et framing) et 18 tests
  registre/CLI. Les interpréteurs de test interdisent réseau, SDK, clients DB,
  subprocessus de collecte et lecture des résultats attendus par le runtime.
- **167 tests réussis** ; sept snapshots individuels et agrégat strictement
  identiques aux références B3.3. Aucun attendu régénéré ; SHA256 du fichier de
  référence toujours `ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
  Les trois CLI B3 sont exécutées sur fixtures et comparées hors date ; les
  tests historiques et les options CLI existantes sont conservés.
- Aucune collecte réelle, inférence, poids, GPU, requête payante, base, migration
  ou planification. Modifications laissées pour revue, sans commit ni push de ce lot.

## B4.4 — budgets, erreurs et reprises (27 octobre 2026)

- Référence : `bd888c4` publié, arbre propre sur `feat/discovery-b4-consolidation` ;
  **167 tests initiaux réussis**. Aucune modification préexistante à déplacer.
- Ajouts : `execution_models.py`, `discovery_execution.py`, `retry_after.py`,
  `synthetic_output.py`, trois modules de tests et `EXECUTION_B44.md`.
- Politiques sans quotas implicites : ressources explicites, limites de dispatches
  et tentatives distinctes, temps monotone, backoff/plafond, codes temporaires et
  choix de retries transport. Horloge UTC, attente et jitter toujours injectés.
- Les reprises sont séparées du transport. `MetadataHTTPError`/`HTTPResult`
  transmettent seulement un Retry-After normalisé optionnel ; headers d'erreur
  toujours vides, aucun corps ou URL réexposé. Les appels anciens restent valides.
- Classification par type/code, sans inspection des messages : refus permanents,
  NIM 404 par tag, 304 sans cache, JSON/contrat/identité, connexion/timeout et budgets.
  Les erreurs permanentes et opérations non idempotentes ne sont pas réessayées.
- Respect des minima Retry-After, report plutôt que réduction des délais ; dates
  IMF/RFC850/asctime et règle de siècle contrôlées avec les horloges simulées.
  La référence documentaire consultée est RFC 9110 ; aucun endpoint fournisseur.
- Résultats success/unchanged/deferred/failed et rapports versionnés hors B2.
  Le moteur n'émet pas unchanged sans cache ; aucun snapshot après erreur,
  dépassement ou sélection incomplète. Chaque source conserve son scope demandé,
  ses compteurs et sa provenance déclarée ; les succès indépendants restent intacts.
- La revue a ajouté des contrôles du coût de construction/validation avant
  publication, des attentes interrompues/trop longues et de la copie de tous les
  plans avant le premier callback. Timeout socket et deadline globale restent
  distincts ; aucune préemption de code bloquant ou compteur interne SDK promis.
- Protection préparée : `discover_sources.py --fixtures --protected-output` ;
  enveloppe synthétique à format distinct, snapshot intérieur intact et rejet
  testé par les deux générateurs avant toute instruction SQL. Aucun changement
  obligatoire des importeurs ou de la sortie brute compatible B4.3.
- Limite explicitée : le B2 brut historique reste importable et son origine ne
  peut pas être prouvée par son hash ; contrat de provenance obligatoire, nouveau
  défaut d'enveloppe ou chemin legacy à examiner avant une évolution incompatible.
- Validation : **229 tests**, dont les 167 existants inchangés et 62 nouveaux
  (48 exécution, 8 Retry-After/transport, 6 protection). Réseau, attente système et
  clients réels interdits/simulés dans les nouveaux tests. Références B3.3 intactes,
  CLI fixtures et historiques préservées, `git diff --check` propre.
- Aucune persistance de checkpoints, collecte réelle, base, poids, GPU, inférence,
  admission au catalogue personnel, migration ou scheduler. Le rapport initial
  conservait ce lot non commité pour revue avant publication.

## Clôture B4.4 — revue avant publication (27 octobre 2026)

- Les modifications locales sont exclusivement celles de B4.4 ; aucun travail
  sans rapport n'est indexé. Budgets, compteurs, idempotence, Retry-After, deadline
  coopérative, lectures interrompues et résultats indépendants ont été relus.
- Les tests vérifient notamment l'absence de dispatch supplémentaire, de sommeil
  réel, de snapshot tardif/partiel et de contenu d'exception dans les manifestes.
  Les générateurs historiques refusent l'enveloppe synthétique avant toute sortie.
- Suite complète : **229 tests réussis** ; `git diff --check` propre et référence
  B3.3 intacte. Aucun défaut démontré justifiant un élargissement du lot.
- Références distantes récupérées : HEAD et origin/feat/discovery-b4-consolidation
  identiques avant le commit, aucune divergence. Publication prévue du seul commit
  B4.4, sans force ; ne pas considérer cette intention comme une confirmation de push.

## Travaux suivants

### Blocage de publication B4.4 — 27 octobre 2026 (historique, résolu ci-dessous)

- Commit local validé : `8ce3a8a23eecf4813c467e01c0c67d08b1eb839d`.
  Message : `feat(discovery): add controlled metadata execution budgets and retries`.
- La première revue automatique a refusé le push faute d'autorisation reconnue.
  Après vérification des lignes 82–87 de la mission utilisateur et du seul commit
  d'avance sans divergence, la même publication limitée au SHA B4.4 a été acceptée.
- Le push a alors échoué : `fatal: could not read Username for 'https://github.com':
  No such device or address`. Aucun identifiant HTTPS Git accessible, aucun push
  effectué, aucun contournement de l'authentification tenté.
- Conformément à l'arrêt demandé en cas d'identifiants nécessaires, B4.5 n'a pas
  commencé et la branche documentaire B5 n'a pas été créée : elle doit partir du
  commit B4.4 effectivement publié. `main` et la branche B3.3 sont préservées.
- Cette note reste non commitée afin de ne pas ajouter un second commit à la
  publication B4.4 autorisée. Une authentification Git sur cette machine est
  nécessaire avant de relancer le push du SHA ci-dessus, puis vérifier le distant.

### Publication B4.4 confirmée et reprise — 27 octobre 2026

- L'utilisateur a publié lui-même B4.4. Après récupération des références,
  `git ls-remote origin refs/heads/feat/discovery-b4-consolidation` confirme
  `8ce3a8a23eecf4813c467e01c0c67d08b1eb839d`, identique à HEAD et à la référence
  distante locale. Aucun nouveau push nécessaire ni effectué par cette reprise.
- Les lignes locales ci-dessus sont conservées comme historique de l'incident ;
  leur demande d'authentification et leur état d'arrêt ne sont plus courants.
- Suite de départ rejouée : **229 tests réussis**. La reprise B4.5 est autorisée,
  avec commits locaux uniquement. B5.0 part séparément du SHA B4.4 publié.

### B4.5 — tranche de primitives locales validée

- Manifestes de provenance versionnés liés à l'identité, au scope et au SHA256
  du snapshot complet. Trois catégories distinctes ; attestations HMAC par
  émetteurs locaux approuvés, aucune prétention de preuve d'origine fournisseur.
- API opt-in de génération SQL protégée : refus des synthétiques, historiques
  inconnus et émetteurs non approuvés avant toute sortie. Importeurs B2 inchangés.
- Cache à source/sélection/ressources/contexte/révisions exacts. `unchanged`
  disponible dans une primitive de revalidation injectée uniquement ; le 304
  du moteur B4.4 conserve son échec sans cache raccordé. Tag NIM toujours mutable.
- Checkpoints POSIX privés versionnés, empreintes vérifiées, écriture atomique,
  verrou exclusif non bloquant, générations explicites et rétention sans purge.
  Tests d'interruptions, redémarrage, chemins/liens, concurrence et idempotence.
- **272 tests réussis**, dont les 229 existants et 43 nouveaux ; références B3.3
  et sorties des sept sources intactes. SHA256 de la référence inchangé :
  `ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
- Voir `CHECKPOINTS_B45.md` pour les limites : raccordement HTTP/budgets/reprise
  inter-sources, gestion des clés, CLI protégée et fraîcheur encore différés.
  B4.5 n'est pas annoncé comme service opérationnel complet. Aucun réseau
  fournisseur, import base, poids, inférence, GPU, scheduler ou push B4.5/B5.

Revoir le registre manuel sur fixtures avant toute extension online. Décisions
de provenance synthétique/réelle, domaines/comptes, NIM multitag et succès partiels
toujours ouvertes. Les retries B4.4 existent uniquement dans l'API d'exécution
injectée ; aucun retry implicite n'a été ajouté aux CLI historiques ou au client HTTP.
B4.5 : cache lié au scope exact, checkpoints atomiques, rétention/reprise après
arrêt, sélection dynamique et garanties des SDK avant budgets de requêtes physiques.
Pas de scheduler ni modification du Personal Model Catalog.
