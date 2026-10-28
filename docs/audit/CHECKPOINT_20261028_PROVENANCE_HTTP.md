# Checkpoint durable — provenance et HTTP conditionnel, phases 0–3

28 octobre 2026. Branche `feat/phases-0-3-integrity-cas` ; HEAD et références
locales `main` / `origin/main` : `5ead5754bd3424356eaf243bf6db271337a8faaa`.
Aucun fetch, staging, commit, push, merge ou rebase dans ce lot. Aucun accès à
VM150, Proxmox ou aux conteneurs/bases ; aucun benchmark ou développement 3.1+.

## Point de départ conservé

[Checkpoint intégrité/CAS lu](CHECKPOINT_20261028_INTEGRITY_CAS_PHASES_0_3.md),
TODO, couverture et contrats B2/B3/B4 examinés avant les corrections.
Départ exact : **11 suivis modifiés et 8 nouveaux non suivis**, tous conservés.
Les travaux CAS, leurs résultats privés et les checkpoints antérieurs ne sont
pas écrasés. Sauvegarde de travail de départ et manifeste SHA256 conservés dans
`/tmp/provenance-http-baseline-a2zb6t4j/` ; pointeur
`/tmp/provenance-http-baseline-current.txt`. Ces copies temporaires complètent
les fichiers durables du dépôt, ne remplacent pas leur préservation.

Sur les 19 fichiers initiaux, 14 sont restés identiques ; cinq sont étendus :
`TODO.md`, `database/poc/B4_JOURNAL.md`, `database/poc/MANUAL_INCREMENTAL_RUN.md`,
`database/poc/discovery_provenance.py`, `docs/audit/PHASES_0_3_COVERAGE.md`.
Les huit nouveaux fichiers CAS initiaux restent identiques, notamment le test,
le contrat d'import, le script de qualification et le précédent checkpoint.

SHA256 des **10 fixtures historiques** et des **135 fichiers privés** inchangés.
Tous les anciens tests sont intacts. Référence littérale B3.3 :
`ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
Suffixe TODO complet depuis le titre `## 3.1 models.dev` :
`52f8b97ef7daa428d3dd1833c625683432ae841a5e73076ba727882d3b4ff66d`.

## Contrats et corrections livrés

Audit et alternatives : [PROVENANCE_HTTP_CONTRACT_AUDIT.md](PROVENANCE_HTTP_CONTRACT_AUDIT.md).
API, limites et différences HTTP : [PROVENANCE_HTTP_PHASE3.md](../../database/poc/PROVENANCE_HTTP_PHASE3.md).

1. `discovery_issuers.py` : autorité injectée en mémoire, HMAC/génération par alias,
   grants source/contexte exacts, rotation vers une nouvelle clé/alias, révocation
   sans réenrôlement d'un ancien alias ou matériau de clé. Aucun bootstrap implicite.
2. La validation de provenance applique ces grants quand un registre est fourni.
   Les anciennes tables de clés restent compatibles comme confiance explicite
   globale ; elles n'acquièrent pas ces garanties de portée/cycle de vie.
3. Publication SQL protégée, archivage et événements complets sous verrou local
   de confiance. Reprise manuelle recontrôlée à chaque source, même après un callback
   de révocation. Test de publication/révocation réellement concurrentes en threads.
4. `conditional_discovery.py` : GET explicite sur transport/normaliseur injectés,
   sans client réseau par défaut. Budgets/retries B4.4 inchangés. Une liaison HMAC
   **séparée** authentifie le cache complet et l'URL exacte, donc ses validateurs,
   révisions et contexte, sans changer le cache/checkpoint/manifeste historique.
5. 200 : JSON strict, métadonnées contrôlées, snapshot complet validé, capture
   explicite, provenance et liaison. 304 : conditions effectivement envoyées,
   représentation connue/authentifiée et validateurs exacts ; conservation de
   l'observation, sa date, son HMAC et sa génération. Reçu local séparé, aucune
   nouvelle observation fournisseur ou prolongation de fraîcheur par 304.
6. Âge maximal explicite depuis la capture, suivi pendant backoff et transport.
   Expiration avant dispatch : GET inconditionnel/200 requis. Expiration pendant
   un 304 : refus. Erreurs transport : aucun repli publié sur les anciennes données.
7. Reprise conditionnelle par descripteur exact `{request, identity, http_binding}`
   avec URL et autorité courantes. Révocation ou altération interdit la reprise ;
   interruption avant archivage préserve l'ancienne génération. Aucun `latest`.
8. ETag unique opaque ASCII et Last-Modified IMF-fixdate canonique ; révisions
   de cache opaques/null, sans blancs/contrôles. NIM reste identifié par resourceId,
   pas son tag. Aucun classement des révisions ou rapprochement interplateforme.

**Compatibilité** : identités/empreintes B2, SourceRecord, sept adaptateurs, formats
B3/B4, générateurs et CLI historiques conservés avec leurs références valides.
La nouvelle liaison n'est pas ajoutée aux anciennes archives. Les valeurs HTTP
malformées/non canoniques autrefois acceptées superficiellement sont désormais
refusées, y compris dans une ancienne entrée validée ; aucune réécriture.
Le `HTTPError(304)` brut reste refusé par B4.4 et les CLI n'activent pas ce profil.

**Frontière de confiance** : HMAC authentifie la déclaration d'un émetteur local,
jamais la véracité des données, une signature fournisseur ou un échange TLS.
Transport/normaliseur/autorité locale sont de confiance. Les tests simulent une
origine avec une clé éphémère, pas une collecte réelle. Le verrou ne coordonne
que les threads d'une même instance, pas des processus ou plusieurs machines.

## Tests et vérifications effectués

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.discovery.test_conditional_provenance -q
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_suites.py -q
git diff --check
git diff --stat
git status -sb
```

| Suite | Résultat |
|---|---:|
| Ciblée provenance/HTTP | 29 OK |
| Discovery complète | 391 OK = 362 précédents + 29 |
| Control Plane | 123 OK |
| Infrastructure simulée | 19 OK |
| Isolation applicative | 63 OK ; aucune qualification OS privilégiée |
| Worker | 48 OK |
| Total suites | **644 OK**, aucun skipped avec les preuves privées présentes |

Les cinq suites ont tourné sous l'UID courant hors sandbox pour leurs sockets
loopback/Unix et tests de permissions temporaires, sans élévation root/installation.
Les 29 nouveaux tests interdisent sockets/DNS/processus/sommeil réel et utilisent
une horloge simulée, sauf synchronisation bornée de deux threads. Ils couvrent
200/304 sans baseline, ETag incohérent, Last-Modified/null, expiration avant/pendant
GET et backoff, domaines/partitions/URL, émetteurs inconnus/révoqués/rotations,
altération, contradictions, révisions malformées, erreurs et reprise interrompue.

Inventaire sans exécution : les points d'entrée `tests.discovery` et la commande
legacy `unittest discover -s database/poc -p 'test_*.py'` exposent les mêmes
**391 identifiants uniques**, sans doublon. Syntaxe Python et whitespace des
fichiers de travail contrôlés ; détection de motifs de credentials/clés privées
sans correspondance, revue du contenu synthétique, aucun nouveau fichier > 1 Mio.
Index vide. Aucun résultat privé ajouté à Git ; aucune assertion historique changée.

## TODO : clôtures exactes et reste à faire

Les **34 lignes initiales ouvertes** restent identiques, dans le même ordre :
phase 1 = 28, phase 2 = 4, phase 3 générale = 2. La clôture T20 du lot précédent
reste valide et n'est pas modifiée. [Classification et dépendances](PHASES_0_3_CLASSIFICATION_20261028.md).
Deux **nouvelles sous-tâches locales** sont cochées : autorité en mémoire avec
contrôles de publication/reprise, et HTTP conditionnel injecté budgété et lié.
Les lignes composites T14/T15 restent PARTIAL, pas un Discovery Service opérationnel.

| Ensemble | État / dépendance restante |
|---|---|
| T14 | Autorité durable, administration/enrôlement, clé hors processus, révocation inter-processus/redémarrage et CLI protégée à définir |
| T15 | Profil HTTP réel par source, stockage des reçus/descripteurs, politique de fraîcheur opérationnelle et intégration complète de reprise à qualifier |
| T09/T11/T12/T13 | Comptes/domaines en stockage, sémantique des révisions distantes, données partielles, NIM multitag et origine obligatoire du B2 brut restent des décisions |
| T16/T34/T35 | Pagination/SDK, budget global, writer protégé et service planifié non activés ; changements de révision réels non vérifiés |
| Phase 2 | Benchmarks et qualifications CAS déjà conservés ; adoption/licence/choix/ADR restent ouverts, aucune nouvelle campagne |
| Infrastructure/worker | Proxmox/backup/restore/POC historiques et pilote OS exigent leurs GO/environnements ; aucun accès dans ce lot |

Le profil strict refuse `Vary`, `no-store`, comptes privés, redirections et
changements/omissions de validateurs sur 304. Élargir ces cas ou réaccepter des
signatures révoquées pour l'historique exige un contrat distinct. Aucune garantie
de fraîcheur distante n'est inventée, ni signature asymétrique/durable installée.
Pas de purge/rétention automatique, scheduler, section 3.1 ou modification du
Personal Model Catalog. Réexaminer les décisions avant toute activation réelle.

## Artefacts existants à préserver

Aucune nouvelle mesure p50/p95, CPU/RAM ou plan moteur dans ce lot ; les anciennes
séries restent la référence et ne sont pas mélangées aux tests HTTP fonctionnels.
[Benchmarks](../../database/poc/ISOLATED_DOCKER_BENCH.md),
[qualification CAS](../../database/poc/INTEGRITY_CAS_PHASE3.md),
[chemins/checkpoint précédent](CHECKPOINT_20261028_INTEGRITY_CAS_PHASES_0_3.md).
Les quatre dossiers locaux ignorés restent privés et inchangés :

```text
database/poc/results/20261028-vm150-isolated/
database/poc/results/20261028-vm150-replay-guard/
database/poc/results/20261028-vm150-isolated-session/
database/poc/results/20261028-vm150-cas/
```

VM150, état seulement **rapporté par le checkpoint antérieur**, non recontrôlé ici :
`/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/`, qualification CAS finale
`attempt-20261028T215853Z-effdf5`, code `code-cas-9ddba473c590/database/poc`.
Les deux conteneurs temporaires et les deux POC étaient arrêtés ; aucune action
sur ces objets, volume, dump, configuration ou artefact dans ce lot.

## Git final et reprise sûre

**16 suivis modifiés, 16 nouveaux non suivis**, comprenant le lot CAS antérieur
et les ajouts de ce lot. Rien d'indexé, ref main et HEAD inchangés. Le détail exact,
avec ce checkpoint et son annexe, est dans
[CHECKPOINT_20261028_PROVENANCE_HTTP_GIT_STATUS.txt](CHECKPOINT_20261028_PROVENANCE_HTTP_GIT_STATUS.txt).
`git diff --stat` n'inclut pas les nouveaux fichiers non suivis.

Pour reprendre : lire ce checkpoint et le contrat, contrôler branche/HEAD/status,
conserver tout le travail CAS/HTTP et les preuves privées, puis lancer les tests
ciblés si le code change et le lanceur central avant revue. Ne pas réenrôler un
émetteur depuis une clé fournie par un document de reprise. Le registre est en
mémoire : toute politique de persistance après redémarrage doit être définie
explicitement avant usage réel. Aucune ancienne observation ne doit servir à
fabriquer la preuve HTTP manquante. Pas de collecte, VM, commit, push, merge ou
rebase autorisé par ce checkpoint ; attendre un nouveau périmètre utilisateur.
