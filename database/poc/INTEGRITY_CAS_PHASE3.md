# Phase 3 — intégrité, provenance et CAS explicite

28 octobre 2026. **IMPLEMENTED / TESTED**, et **VERIFIED sur bases synthétiques
isolées** pour les cas ci-dessous. Branche `feat/phases-0-3-integrity-cas`, base
`5ead5754bd3424356eaf243bf6db271337a8faaa`. Aucun commit/push/merge/rebase.
Ce lot n’active ni import automatique, ni collecte fournisseur, ni chapitre 3.1+.

## Défauts reproduits et corrigés

- Une validation B2 sans `captured_at`, ou avec `null`, utilisait implicitement
  la date courante du constructeur. Le lecteur exige désormais les cinq champs
  exacts et une date explicite valide ; le constructeur peut toujours dater une
  nouvelle observation. Les générateurs refusent ces entrées avant sortie SQL.
- Des champs d’enveloppe non liés au contenu étaient acceptés. Ils sont refusés,
  sans retirer les champs inconnus autorisés dans attributs/métadonnées/scopes.
- L’égalité Python assimilait false/0, true/1 et 0/0.0 dans les comparaisons de
  scope. La comparaison canonique distingue les types JSON, y compris pour le
  scope d’une attestation ; une altération false→0 du manifeste est refusée.
- Le plan traitait deux écritures du même instant avec fuseaux différents comme
  un conflit, et utilisait un flottant pour comparer les dates. La transition
  commune compare les instants exacts sans modifier leur représentation B2 ni
  perdre les microsecondes ; les révisions restent opaques, sans ordre lexical.
  Cela ne qualifie pas une précision nanoseconde ou l’horloge des fournisseurs.
- Le CSV PG confondait révision `null` et chaîne vide. Une cellule vide non
  citée reste NULL ; une chaîne vide est citée. Virgules et guillemets sont
  échappés. La distinction est qualifiée réellement sur les deux moteurs.
- Les générateurs prennent une copie défensive de l’entrée : une mutation du
  snapshot par le caller durant l’écriture du stream ne modifie plus le SQL.

Les clés, empreintes et formats B2/B3/B4, les sept normaliseurs et les fixtures
historiques restent inchangés. Le SQL CSV change volontairement pour conserver
la valeur vide ; aucun ancien fichier de résultats n’est réécrit.

## Contrat CAS optionnel des générateurs

```python
# Génération uniquement : ces fonctions n’ouvrent jamais de connexion DB.
emit_pg(after_snapshot, stream, expected_snapshot=before_snapshot)
emit_surreal(after_snapshot, stream, expected_snapshot=before_snapshot)

# Explicitement : toutes les clés observées doivent être absentes ou déjà
# dans l’état voulu. Aucun remplacement aveugle d’une ligne existante.
emit_pg(initial_snapshot, stream, expected_snapshot=None)
```

Omettre le keyword conserve le chemin historique à garde temporelle ; la CLI
historique ne choisit pas automatiquement une baseline et n’active pas le CAS.
Les scopes doivent être identiques et les transitions monotones en date de
capture ; cette date n’établit pas l’ordre des versions chez le fournisseur.

Pour chaque ligne observée, accepter seulement : absence attendue et effective,
ligne complète identique à la baseline attendue, ou état cible déjà appliqué.
Une baseline attendue mais absente, ou une ligne concurrente différente, annule
la transaction. Comparer la ligne entière, pas seulement son digest déclaré.
Une ressource non observée n’est jamais supprimée ni rafraîchie artificiellement.
Après une collecte partielle, réintroduire une clé dont l’état DB n’est pas décrit
par la baseline peut donc être refusé : réconcilier explicitement, pas de repli.

PG : deux stages COPY temporaires, verrou SHARE ROW EXCLUSIVE, contrôles de date
et CAS sous READ COMMITTED, puis upsert. SurrealDB : même transaction explicite
pour contrôles et écritures ; conflits concurrents refusés au lieu de poursuivre.
La borne complète de 512 Kio UTF-8 reste appliquée à la sortie Surreal.

## Provenance de la transition protégée

`discovery_provenance.emit_protected_transition(before_cache, after_cache,
context=..., trusted_issuers=..., engine=..., stream=...)` valide les caches
complets, signatures des émetteurs déjà approuvés, identité de source/sélection,
contexte et transition avant génération CAS. `before_cache=None` est un premier
import à absence attendue. Synthétique, origine historique inconnue, émetteur
inconnu, contexte différent et compte non anonyme sont refusés sans sortie.

Le contexte cible est fourni par le caller, pas lu/vérifié en base. Cette API
ne prouve pas l’isolation physique domaine/compte et ne l’active pas ; les comptes
privés sont volontairement refusés. HMAC lie un émetteur local au snapshot exact,
pas à une vérité fournisseur ; les clés des tests sont éphémères et les signatures
contrôlées y sont simulées. Enrôlement/rotation/révocation et CLI restent ouverts.
Le plan `incremental_import_plan` reste `executable=false` ; son champ legacy
reste false parce que le chemin brut par défaut n’exécute pas automatiquement
ces préconditions. Aucun changement implicite de confiance ou de production.

## Qualification réelle sur le banc temporaire

Mode distinct `--cas-only --execute` : nouvelles bases synthétiques dans les
deux conteneurs temporaires déjà autorisés. **Aucune restauration, aucune nouvelle
mesure de benchmark, aucun SELECT sur POC historiques.** Images exactes locales
PostgreSQL 16.15 / SurrealDB 3.3.4 et limites du banc conservées.

| Scénario | PostgreSQL | SurrealDB |
|---|---|---|
| Absence attendue alors qu’une autre ligne existe | Refus CAS | Refus CAS |
| Deux écrivains depuis la même baseline | Un commit, un refus CAS ; attente de verrou observée | Un commit, une transaction refusée ; démarrage coordonné |
| Date plus récente mais baseline obsolète | Refus CAS | Refus CAS |
| Baseline réconciliée puis rejeu déjà appliqué | Succès idempotent | Succès idempotent |
| Interruption / échec après écriture avant commit | Fermeture psql avec transaction ouverte : rollback | THROW après premier upsert : rollback |
| Nouvelle tentative après interruption | Succès sans perte | Succès sans perte |
| Digest déclaré identique mais attribut false→0 corrompu | Refus sur ligne complète | Refus sur ligne complète |
| Révisions nulles et vides | Distinction conservée | Distinction conservée |
| Baseline attendue mais ligne manquante, autre ajout dans le même lot | Refus, aucun ajout résiduel | Refus, aucun ajout résiduel |
| Ligne non observée et snapshots d’entrée | Conservés | Conservés |

Première série réussie : `attempt-20261028T215506Z-0b4787`.
Série finale étendue : `attempt-20261028T215853Z-effdf5`, **22:58:53–22:58:58
Europe/Paris**. PG observe réellement le second writer en attente ; Surreal
coordonne deux sessions séparées avec une pause transactionnelle de 500 ms.
Ces délais sont des outils de qualification, pas des latences de benchmark.
Échantillon borné : pas de preuve de débit sous forte concurrence ou d’absence
universelle de blocage/starvation. Neuf ressources finales, empreinte normalisée
commune `764429f0b25be9a53dbabfd6ab90679239ccccc540b86567fafec1335d47fd78`.

La corruption est injectée puis rétablie uniquement dans une ligne créée pour
ce nouvel essai. Aucun état/donnée préexistant historique n’est modifié.
Les deux conteneurs temporaires sont arrêtés ; fingerprints des POC historiques
identiques avant/après. Aucun changement Proxmox, système, réseau hôte ou GPU.

Racine VM conservée : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/`.
Code final : `code-cas-9ddba473c590/database/poc`, bundle
`bundle-cas-9ddba473c590.tgz`, SHA256
`d09474dece4f6f9d71955d18409d9809259460e481936979d579ed9a7445bba0`.
Archive de revue `review-cas-9ddba473c590.tgz`, SHA256
`9d55688fea2ea0e147113508e6ff41cc3fd41ae6c5c9a33c6bf8de2091af0ed8`.
Copie locale **privée ignorée par Git** : `results/20261028-vm150-cas/`
(18 preuves JSON + manifeste), empreintes/tailles vérifiées. Les anciens bundles,
essais, données et exports restent conservés, sans suppression.

La copie défensive et son test ont été ajoutés après le bundle exécuté : les
empreintes des dix générations SQL comparées au code du bundle sont identiques.
Aucun deuxième passage sur les benchmarks existants pour cette modification.

## Validation locale et limites restantes

`python3 tests/run_suites.py -q` : **615 succès**, dont 362 Discovery (15 nouveaux),
123 Control Plane, 19 infrastructure, 63 isolation applicative et 48 worker.
Tests ciblés après modifications, références B3.3 intactes. Le contrôleur de banc
est toujours opt-in ; importer les modules n’exécute aucune qualification.

Restent ouverts : writer/CLI de production avec origine obligatoire, stockage
cloisonné, ordre/fraîcheur des révisions réellement sondées, reçus 304 raccordés,
gestion des émetteurs, SDK/pagination/quotas, scheduler et rétention. CAS protège
un état attendu, pas l’exactitude d’une observation récente mensongère. Les anciens
SQL et le mode brut sans baseline n’acquièrent pas cette protection rétroactivement.
