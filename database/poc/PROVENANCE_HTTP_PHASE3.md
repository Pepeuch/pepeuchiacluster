# Phases 0–3 — provenance et HTTP conditionnel

28 octobre 2026. Lot local sur `feat/phases-0-3-integrity-cas`, après le
[contrat intégrité/CAS](INTEGRITY_CAS_PHASE3.md). Audit préalable et choix
additifs : [revue des contrats](../../docs/audit/PROVENANCE_HTTP_CONTRACT_AUDIT.md).
Aucun appel fournisseur, accès VM/base, benchmark, scheduler ou développement 3.1+.

## Autorité des observations

`discovery_issuers.IssuerRegistry` est une autorité **locale en mémoire** fournie
explicitement par l'appelant. Chaque alias désigne une génération de clé HMAC
et des autorisations exactes `(source, domain, account_partition, representation)`.
Un émetteur inconnu, révoqué, doté d'une autre clé ou sans autorisation pour ce
contexte est refusé. Les grants sont détachés et immuables après enrôlement.

`enroll` exige une clé injectée d'au moins 32 octets et des grants explicites ;
`rotate` enrôle un nouvel alias et une nouvelle clé avec les mêmes grants avant
de révoquer l'ancien. Aucun alias ou matériau de clé connu, même révoqué, ne peut
être réutilisé dans ce registre. Une rotation invalide laisse l'ancienne génération
active. Aucun enrôlement, renouvellement ou recours à une autre clé implicite.
Les anciennes observations signées par une génération révoquée deviennent
inutilisables pour la publication et la reprise ; les fichiers sont conservés.

La validation B4, l'archivage, les générateurs protégés et le runner manuel
acceptent ce registre via leur paramètre `trusted_issuers`. La validation vérifie
alors la portée source/contexte en plus du HMAC. Le runner recontrôle chaque cache
repris et chaque événement complet, même après un callback qui change la confiance.
Avec ce registre, un verrou réentrant couvre validation et publication locale :
la révocation depuis un autre thread prend effet avant ou après cette publication,
sans fenêtre entre validation et renommage du checkpoint. Cette coordination
concerne **une instance dans un processus**, pas une autorité distribuée. Un stream
ou callback est un collaborateur local de confiance, pas une frontière OS.

Les dictionnaires historiques de clés restent acceptés par les anciennes API :
ils représentent une confiance explicite globale, sans grants ni cycle de révocation
concurrente. Le nouveau chemin HTTP exige `IssuerRegistry`. Son propriétaire et
le code qui possède les clés restent dans le domaine de confiance. Un vérificateur
HMAC peut aussi signer ; aucune preuve de non-répudiation ou signature fournisseur.
Une attestation authentifie une déclaration locale, **pas sa véracité**, ni la
réalité d'une collecte distante. Les fixtures utilisent une clé éphémère aléatoire.

## Liaison HTTP distincte des formats historiques

Le HMAC B4 protège snapshot, date, scope et contexte, mais pas les validateurs du
cache. Recalculer les digests d'une archive ne suffit donc pas à authentifier leur
association. `conditional_discovery.py` ajoute un document séparé :

```text
pepeuch-ai.http-representation-binding/v1
  issuer, target_url, cache_sha256, attestation
```

Son HMAC couvre le document hors attestation ; le SHA256 couvre **tout le cache**,
donc les validateurs, la requête/révisions, le contexte et l'observation signée.
`validate_binding` exige la confiance courante pour les deux signatures et l'URL
exacte. Une liaison manquante, modifiée ou associée à un autre chemin est refusée.
Aucun champ n'est ajouté au B2, au manifeste B4, au cache v1 ou à l'archive v1.
Pas de ressignature automatique des anciennes archives dépourvues de cette liaison.

## Profil GET explicite et conservateur

`run_conditional` reçoit obligatoirement un `SourceTask`, runtime/horloges, URL,
`HTTPPolicy`, transport `fetch` et normaliseur injectés, registre/clé/contexte,
instant local et âge maximal. Il n'instancie aucun client réseau par défaut.
Un GET par tentative passe par `AttemptContext.request` et les budgets B4.4 ;
les retries, limites et diagnostics existants s'appliquent. Aucun `HTTPError(304)`
brut n'est promu en succès dans le moteur ou les CLI historiques.

Le transport renvoie explicitement `ConditionalResponse(status, body, validators,
target_url, vary=(), no_store=False)`. Seules des représentations JSON anonymes
fixes sont prises en charge : hôte HTTPS enregistré et autorisé, contexte domaine
identique, URL finale inchangée, corps borné, aucun `Vary` ni `no-store`.
Les sources locales et SDK ne passent pas par ce profil. Le transport et le
normaliseur sont des collaborateurs de confiance : une réponse injectée n'est
pas une preuve TLS ou fournisseur. Aucun des sept adaptateurs n'est migré ici.

| Situation | Résultat du nouveau chemin |
|---|---|
| 200 valide | JSON strict sans clés sensibles, normalisation complète B2, nouvelle observation datée explicitement, provenance et liaison HTTP |
| 304 lié à un GET conditionnel valide | `unchanged`, cache/snapshot/date/provenance/liaison antérieurs identiques ; reçu de vérification séparé |
| 304 sans représentation connue, sans condition envoyée ou avec corps | Refus sans publication ni nouvelle observation |
| 304 aux validateurs absents/différents de ceux envoyés | Refus ; une nouvelle réponse 200 est requise |
| Même instant et observations contradictoires | Refus par le contrat commun de transition |
| Payload B2 changé avec ETag inchangé | Refus ; en absence d'ETag des deux côtés, même contrôle avec Last-Modified |
| Domaine, partition, sélection, représentation, URL ou attente de révision différents | Refus de réutilisation avant transport |
| Révocation pendant le transport ou avant archivage/reprise | Refus avec la confiance courante |
| Erreur ou budget dépassé | Aucun cache antérieur publié en repli ; résultat d'échec/report normalisé |

L'âge est calculé depuis `captured_at` avec l'instant local explicite, puis le
temps monotone écoulé. Maximum admissible : de zéro à sept jours, choisi par
l'appelant, **pas un engagement fournisseur**. Une entrée future est refusée.
L'expiration avant dispatch, y compris après backoff, supprime les conditions :
200 requis. Une entrée expirant pendant le GET ne peut plus produire `unchanged`
(`validated_cache_required`). Un 304 ne renouvelle jamais sa capture ou cet âge.
Une réponse 200 peut confirmer le même contenu à une nouvelle date, sans changer
l'identité B2. L'horloge locale, le transport et le normaliseur doivent être fiables.

Les révisions restent des chaînes opaques ou `null` explicitement inconnu ; aucun
classement lexical, assimilation ETag/SHA ou changement de règle NIM. Des attentes
de révision sont optionnelles mais exactes ; une attente contradictoire est refusée.
Les chaînes vides/blanches, trop longues ou contenant des contrôles sont refusées
par la requête de cache. Cela ne modifie pas `SourceRecord` ou les snapshots B2
historiques qui peuvent conserver une révision vide.

## Validateurs et compatibilité

Les ETag acceptés sont des jetons ASCII opaques entre guillemets, éventuellement
préfixés par `W/` ; le jeton vide et le backslash littéral sont conservés. Listes,
espaces internes et suffixes malformés sont refusés. Last-Modified doit être une
date IMF-fixdate canonique avec jour cohérent. Ce profil conserve la limite ASCII
et 256 caractères préexistante. Contrairement à un cache HTTP général, il exige
l'égalité exacte des validateurs rendus sur 304 : omission ou changement de force
nécessitent un 200. Le standard autorise d'autres cas ; ce choix conservateur ne
prétend pas implémenter tout HTTP. Voir [RFC 9110, validateurs et conditions](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2)
et [RFC 9111, mise à jour après validation](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.4).

**Durcissement intentionnel** : certains ETag malformés et dates arbitraires que
l'ancien validateur superficiel acceptait sont désormais refusés, y compris dans
une ancienne entrée v1 soumise à validation. Les fichiers ne sont pas réécrits.
Les formats valides, sorties des sept sources, clés/empreintes B2 et références
B3.3 restent inchangés. Ne pas contourner un refus en supprimant des champs ou
en fabriquant une attestation de l'ancien cache.

## Reprise sans nouvelle confiance

`archive_conditional` vérifie la liaison et archive le cache avec le mécanisme
POSIX privé existant. Il renvoie `{request, identity, http_binding}` ; la liaison
accompagne ce **descripteur distinct**, sans modifier l'archive historique.
`restore_conditional` exige ce descripteur exact, son URL et l'autorité courante.
Un chargement d'archive B4 seul ne suffit pas à autoriser un GET conditionnel.
Un 304 archivé rend la même identité et le même fichier. Une interruption avant
publication préserve l'ancienne génération ; aucune sélection `latest`, purge
ou substitution automatique. L'appelant doit conserver le descripteur hors logs
sensibles, dans son espace privé. Son stockage durable n'est pas installé ici.

## Validation locale et décisions restantes

Fixture additive : `fixtures/http_conditionals.synthetic.json`, explicitement
synthétique, sans identifiants de connexion ni signatures/clefs enregistrées.
29 nouveaux cas : erreurs, 200/304, expiration pendant requête/backoff, révocation,
rotation, altération des validateurs, contradictions, portée, reprise interrompue
et publication concurrente. Le réseau réel, DNS, lancement de processus et sommeil
réel sont interdits par ces tests.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.discovery.test_conditional_provenance -q
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_suites.py -q
git diff --check
```

Résultat : **644 succès**, dont Discovery 391, Control Plane 123, infrastructure
19, isolation applicative 63, worker 48. Les 615 cas précédents restent présents.
Les tests OS privilégiés et la collecte réelle ne sont pas qualifiés par ce résultat.

Restent ouverts : administration/enrôlement durable et stockage sûr des clés,
révocation entre processus/redémarrages, signature asymétrique et audit de confiance,
CLI protégée, intégration réseau réelle et politique HTTP par fournisseur,
`Vary`/représentations privées et isolation du stockage, révisions distantes et
horloges, persistance/rétention des reçus de revalidation, pagination/SDK et quotas
globaux, activation d'un writer protégé. Une acceptation future d'anciennes signatures
après rotation nécessite un contrat distinct ; aucun mode « clé révoquée acceptée
pour historique » n'est ajouté. Les 34 lignes composites restent ouvertes.
