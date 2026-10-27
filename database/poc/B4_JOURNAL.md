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

## Travaux suivants

B4.1 : primitives communes et durcissement conservateur ; B4.2 : client HTTP borné
injectable sans retry et interface SDK ; B4.3 : conception d'un registre explicite.
Pas de scheduler ni modification du Personal Model Catalog.
