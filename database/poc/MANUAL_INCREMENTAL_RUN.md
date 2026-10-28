# Exécution incrémentale manuelle — primitives raccordées, production bloquée

28 octobre 2026. IMPLEMENTED / TESTED hors ligne. Les anciens adaptateurs,
CLI, formats B2/B3, migrations et références B3.3 sont inchangés. Pas de scheduler,
collecte distante, import DB, inférence ou accès GPU. Discovery Cache reste
distinct du Personal Model Catalog et indépendant des deux moteurs.

## Ce que le lot réalise

`manual_discovery_run.py` raccorde les tâches et budgets B4.4 aux checkpoints
immuables B4.5. La CLI accepte **exclusivement les fixtures synthétiques** des
sept sources. L’API reçoit explicitement opérations, horloges et contextes ;
elle n’instancie aucun transport réseau. Une source incomplète ne produit pas
de snapshot ; les sources complètes sont archivées indépendamment et le manifeste
global reste incomplet. Son périmètre demandé n’est pas réduit pour masquer un échec.

Chaque publication émet immédiatement une ligne JSON d’événement contenant la
requête B4 et l’identité de génération. Une interruption laisse les générations
déjà publiées intactes. Reprise par sélection **explicite** de ces descripteurs,
sans `latest`, écrasement ni purge. Une interruption avant émission de l’événement
peut laisser une génération orpheline à examiner manuellement ; aucune adoption
automatique d’un fichier inconnu. Un callback applicatif peut conserver ces événements.

Exemple hors ligne ; ce répertoire temporaire ne contient que les fixtures :

```bash
PEPEUCH_ARCHIVE_TEST="$(mktemp -d /tmp/pepeuch-discovery-archive.XXXXXX)"
python3 database/poc/manual_discovery_run.py --fixtures \
  --archive-dir "$PEPEUCH_ARCHIVE_TEST" \
  --now 2026-10-28T00:00:00+00:00 --max-age-seconds 86400
```

Pour `--resume`, fournir un JSON `{source: {request: ..., identity: ...}}` construit
à partir des événements retenus. Les descripteurs sont tous validés avant toute
opération. Répertoire POSIX préexistant privé, pas de symlinks, pas de partage
NFS/SMB ; le verrou B4.5 protège chaque publication, pas un run concurrent complet.
Le contrat de run reste mono-opérateur ; ordonnancement concurrent non qualifié.

Fraîcheur : `now` et durée maximale explicites, 0 à 7 jours ; l’âge est fondé sur
`captured_at` et n’est jamais remis à zéro par la reprise. Une observation future
est refusée ; une génération trop ancienne est observée à nouveau. Le statut
`resumed_cached` signifie réutilisation autorisée par cette politique locale,
**pas HTTP 304 ni preuve de fraîcheur distante**. Les fixtures conservent leur
date originale même lorsqu’elles sont relues. L’identité B2 exclut la date,
mais le checkpoint inclut tout le contenu : deux captures du même snapshot B2
restent deux générations distinctes.

## Provenance, partitions et limites

Chaque cache porte son contexte domaine/partition/représentation. Une reprise
dans un autre contexte est refusée ; synthétique, contrôlé et historique inconnu
ne sont pas interchangeables. Les opérations contrôlées injectées exigent un
émetteur déjà enrôlé avant exécution ; aucun enrôlement/rotation/révocation implicite.
HMAC établit la responsabilité locale d’un émetteur, jamais la véracité du fournisseur.
La CLI ne propose ni clé, ni collecte réelle, ni export SQL.

Les requêtes de cache comportent les révisions observées, y compris `null`. Un
descripteur explicite n’établit pas la révision **actuelle distante**. Les vrais
changements de révision, les reçus HTTP conditionnels et leurs ETag ne sont pas
validés par la reprise locale. La connexion 304/transport/moteur reste un lot
distinct ; ne pas transformer un succès budgété en `unchanged` en changeant B4.4.

La CLI précharge les fixtures locales ; les budgets d’opération ne prétendent
pas inclure ce préchargement ni les publications disque. Budget coopératif par
source : pas de préemption d’un SDK opaque, plafond global, concurrence par hôte
ou pagination distante. Erreurs normalisées, sans texte d’exception ou corps HTTP.
NIM conserve `resourceId` comme identité ; multitag toujours non pris en charge.

## Plan d’import incrémental à examiner

`incremental_import_plan.plan_import` produit un **plan non exécutable** à partir
de caches validés. Il refuse baseline historique inconnue, changement de partition,
origine ou sélection, capture plus ancienne et observations contradictoires à
la même date. Chaque upsert porte la précondition précédente (payload, snapshot,
date) ou l’absence attendue, avec acceptation d’un rejeu déjà appliqué. Aucune
ressource non observée n’est supprimée. Le plan possède `delete_actions: []`.

Les tests injectent un échec dans un oracle en mémoire : transaction atomique
et préfixe d’instructions déjà appliquées, rejeu idempotent, concurrence simulée,
absence de mutation et conservation des lignes non observées. **Cela ne valide
aucun moteur réel.** Les générateurs B2 ne mettent pas ces préconditions CAS en
œuvre. Depuis la reprise du 28/10, le SQL régénéré porte une garde transactionnelle
d’antériorité, qualifiée en base synthétique : [preuve et limites](REPLAY_GUARD_PHASE3.md).
Les anciens fichiers SQL restent sans cette garde ; le plan reste non exécutable.

Avant un exécuteur : vérifier l’état DB, implémenter CAS/staging atomique adapté,
préserver les observations inter-sources, traiter les préconditions échouées et
tester interruptions réelles PG/Surreal en environnement approuvé. Les identités
B2 n’incluent pas les comptes/domaines : un contexte de cache isolé ne suffit
pas à isoler les écritures dans une table globale. Aucun import privé/multi-compte
ne doit être activé avant cette décision, sans changer les clés historiques.

## Reste explicitement ouvert

Émetteurs et CLI protégée, contrats de révisions immuables/mutables, comptes/domaines,
pagination/SDK et budgets globaux, reçus HTTP 304 intégrés, rétention avec purge
autorisée, surveillance/scheduler et service de production. Les sept snapshots
sur fixtures restent identiques aux sorties historiques ; les références B3.3
et les tests existants servent de garde de non-régression.

## Validation DB ajoutée après autorisation du banc isolé

Le [banc réel du 28 octobre](ISOLATED_DOCKER_BENCH.md) a depuis validé les deux
moteurs sur données exclusivement synthétiques : roundtrips des sept sources,
types distincts, valeurs inconnues, révisions simulées, non-suppression, scopes,
identités interplateformes, échecs/réimport et restauration du cache. Les lots
transactionnels du banc ont leur propre manifeste/reçus et leur reprise vérifiée.
Ils ne constituent pas l’exécuteur général du Discovery Service et ne modifient
pas les générateurs legacy.

Le risque de remplacement par un ancien snapshot a été reproduit réellement
avec le chemin legacy, puis l’état synthétique rétabli. Ces résultats historiques
sont conservés ; une qualification distincte valide ensuite la garde des dates du
SQL régénéré. Le plan ci-dessus reste non exécutable ; cela n’active pas un writer
de production avec CAS, provenance obligatoire et isolation de stockage.
Les révisions fournisseur, les politiques domaines/comptes, l’ordre de publication
et la collecte/surveillance planifiée restent ouverts. POC historiques préservés.
