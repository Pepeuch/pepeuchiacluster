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

## Travaux suivants

Revoir le registre manuel sur fixtures avant toute extension online. Décisions
de provenance synthétique/réelle, domaines/comptes, NIM multitag et succès partiels
toujours ouvertes ; aucun checkpoint, retry ou traitement périodique ajouté.
Pas de scheduler ni modification du Personal Model Catalog.
