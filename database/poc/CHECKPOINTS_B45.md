# B4.5 — provenance, cache validé et reprise locale

27 octobre 2026. Base publiée : `8ce3a8a23eecf4813c467e01c0c67d08b1eb839d`.
Tranche locale additive, hors réseau, hors base et sans raccordement aux sept
adaptateurs. Les CLI B3/B4.3 et le moteur B4.4 conservent leur comportement.

## Contrats et frontière de confiance

`discovery_provenance.py` définit `pepeuch-ai.discovery-provenance/v1` :

| Catégorie | Sens | Import protégé | Base de revalidation |
| --- | --- | --- | --- |
| `synthetic` | Fixture ou simulation explicitement déclarée | Refus | Simulation hors ligne uniquement |
| `controlled_observation` | Déclaration authentifiée par un émetteur local approuvé | Accepté si attestation valide | Acceptée si cache complet et contexte identique |
| `historical_unknown` | Historique dont l'origine n'est pas démontrée | Refus | Refus |

Le manifeste lie le `snapshot_id`, le SHA256 du **snapshot complet canonique**,
le scope et le contexte de validation. L'empreinte supplémentaire couvre aussi
`captured_at`, que l'identité B2 exclut volontairement. Aucun champ B2 n'est ajouté
ou recalculé autrement. L'attestation HMAC-SHA256 couvre tout le manifeste hors
attestation ; clés d'au moins 32 octets injectées, jamais sérialisées. Le vérificateur
doit recevoir séparément sa table d'émetteurs approuvés ; aucune clé fournie dans
le document ne devient une ancre de confiance.

**HMAC prouve la possession d'une clé locale, pas l'origine fournisseur ni la
réalité d'une collecte.** `synthetic=false`, un hash ou une signature auto-déclarée
ne suffisent pas. Un émetteur malhonnête possédant la clé peut signer une fixture.
Les tests d'acceptation utilisent un émetteur simulé et une clé éphémère ; ils
n'établissent aucune observation réelle. Le scope MoArk explicitement synthétique
est refusé même à l'émission d'une attestation contrôlée.

L'enrôlement des émetteurs, le stockage/rotation/révocation des clés et une future
émission après collecte contrôlée restent à valider avant usage réel. HMAC partagé
permet au vérificateur de signer : une signature asymétrique devra être étudiée
si les domaines de confiance se séparent. Aucun coffre de secrets n'est créé ici.

## Chemin d'import protégé, uniquement opt-in

Point d'entrée Python :

```python
emit_protected(snapshot, provenance, trusted_issuers=trusted_keys,
               engine="pg", stream=output)
```

Ce chemin valide l'intégralité du snapshot, la liaison du manifeste et
l'attestation d'un émetteur approuvé, puis exige `controlled_observation`.
Le générateur historique choisi travaille dans un tampon avant publication :
aucune instruction SQL n'est publiée après refus. La sortie acceptée est identique
à celle du générateur B2, sans suppression ni accès base. **Générer n'est pas importer.**

Pas de nouvelle CLI de signature ou d'import : son interface de confiance et
son stockage des clés exigent une décision séparée. L'API opt-in est testée,
aucun pipeline automatisé ne l'invoque. Les importeurs historiques restent
inchangés : leur invocation sur du B2 brut est manuelle et ne prouve aucune origine.
Aucun repli silencieux vers ces importeurs, aucun déballage automatique des
enveloppes synthétiques. Un utilisateur peut toujours contourner volontairement
la protection en appelant lui-même le chemin legacy ; cette limite est explicite.

## Cache au contexte exact

`validated_discovery_cache.py` définit `pepeuch-ai.validated-discovery-cache/v1`.
Chaque entrée contient un snapshot d'une seule source, son empreinte, sa provenance,
sa validation complète, les ressources demandées, la sélection B2 exacte, les
révisions attendues (y compris `null`) et les validateurs HTTP optionnels.

Le contexte fermé contient `domain`, `account_partition`, `representation` :
alias publics sans URL, compte personnel, en-tête d'authentification ou secret.
Il isole les comptes et représentations sans mettre les identifiants dans les
payloads B2. Le gestionnaire futur devra assigner ces partitions à partir de la
configuration de confiance ; aucun domaine n'est découvert ou autorisé ici.
Ordre des IDs dans le scope et valeurs inconnues restent inchangés.

`reuse_not_modified` exige une entrée complète et revalidée, la même requête
canonique (source, scope, ressources, contexte, révisions), et au moins un validateur
conditionnel envoyé correspondant exactement à l'entrée. Le résultat explicite
`unchanged` contient une copie du snapshot antérieur ; il ne rafraîchit pas sa date.
L'origine historique inconnue est refusée. Les validateurs sont bornés et refusent
les caractères de contrôle ; ce ne sont jamais des en-têtes arbitraires.

**Contrat injecté** : le futur appelant devra attester qu'un vrai HTTP 304 répond
à cette requête conditionnelle. Aucune requête n'est faite et aucun adaptateur
n'est raccordé ici ; une fonction hors transport ne peut prouver un échange HTTP.
Le moteur B4.4 continue de classer 304 sans cache comme échec
`validated_cache_required`. Aucune validation conditionnelle implicite n'est
ajoutée aux CLI. L'intégration budgétée et les reçus HTTP sont différés.

Les tags NIM sont mutables : une égalité de tag n'autorise aucune réutilisation
sans validation conditionnelle correspondante. `resourceId` reste l'identité ;
le multitag dans un même snapshot n'est toujours pas pris en charge. Aucun
rapprochement interplateforme, admission au Personal Model Catalog ou effacement.

## Checkpoints locaux atomiques

`discovery_checkpoints.py` définit `pepeuch-ai.discovery-checkpoint/v1` :

1. Valider et copier toute l'entrée avant la moindre écriture.
2. Ouvrir chaque composant du chemin absolu avec des descripteurs de répertoire
   et `O_NOFOLLOW` ; refuser `..`, liens, répertoire final non privé/non propriétaire,
   fichiers spéciaux, fichiers accessibles à d'autres utilisateurs et hardlinks.
3. Obtenir un verrou POSIX exclusif non bloquant ; refuser un écrivain concurrent.
4. Écrire un temporaire exclusif dans le même répertoire, compléter les écritures
   courtes, puis `fsync` du fichier.
5. Publier par renommage atomique sous verrou, puis `fsync` du répertoire.

Nom final : `<SHA256 requête>.<SHA256 entrée>.json`. Une génération existante est
comparée octet par octet et jamais réécrite ; un conflit/corruption fait échouer
l'opération. Les différentes observations et validateurs produisent des générations
distinctes. Le chargement exige la requête **et la génération explicites**, vérifie
le nom, l'enveloppe, les deux empreintes, le B2, le cache et la provenance.
Taille maximale : 16 Mio ; JSON strict, sans clés répétées ni nombres non finis.

Support promis : **un répertoire local POSIX privé et des écrivains coopérant au
même verrou**, testé sous Linux. Aucune garantie NFS/SMB/Windows, ni contre le
propriétaire malveillant du répertoire. Les hashes détectent la corruption ; ils
n'authentifient pas les validateurs HTTP face à un tel propriétaire. La provenance
contrôlée possède séparément son attestation. Les clés restent hors checkpoints.
Les lecteurs voient un fichier complet ou son absence ; aucun pointeur `latest`.

Avant publication, une interruption laisse l'ancienne génération intacte. Après
publication, répéter la même écriture est idempotent. Une erreur de `fsync` après
renommage peut laisser la génération publiée : vérifier puis répéter. Les tests
simulent des interruptions de processus ; ils ne prouvent pas la tenue d'un disque
à une coupure électrique. Les résidus `.pending-*` d'un processus tué sont ignorés
et conservés ; seuls les temporaires propres à l'appel courant sont nettoyés.

**Rétention** : conservation illimitée par défaut, aucune suppression automatique,
aucune expiration/prune, y compris après erreur d'une autre source. Prévoir une
purge manuelle revue et sauvegardée avant le futur usage prolongé ; saturation
disque = échec visible, jamais effacement des observations anciennes.

## Validation et travaux différés

Les tests `test_recovery_b45.py` couvrent les trois provenances, refus avant SQL,
cache absent/incomplet/incompatible, scope/domaines/comptes, révisions et NIM,
copie défensive, intégrité, chemins/liens/verrou, écritures courtes, interruptions,
redémarrage, idempotence, conservation des générations, succès indépendants,
champs sensibles et aller-retour des sept sources sans changement B2.

Cette tranche livre les primitives et leurs garanties locales. **B4.5 n'est pas un
service de collecte récupérable opérationnel** : restent l'intégration des reçus
HTTP 304 dans les budgets, les politiques de fraîcheur/expiration, les clés et la
CLI protégée, puis l'orchestration de reprise inter-sources. Pagination distante,
concurrence par hôte, quotas internes SDK et budget global exigent leurs propres
contrats ; ils ne sont pas implémentés. Pas de réseau fournisseur, poids,
inférence, GPU, base, migration ou scheduler dans ce lot.
