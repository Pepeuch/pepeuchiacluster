# Audit de contrat — provenance et HTTP conditionnel

Lot local du 28 octobre 2026, branche feat/phases-0-3-integrity-cas,
HEAD 5ead575. Le lot CAS non committé (11 suivis modifiés, 8 nouveaux)
est préservé. Aucune VM/base/Proxmox, collecte réelle ou nouveau benchmark.

## Contrats présents et défauts ciblés

B2 et ses empreintes restent la référence. B4.5 lie par HMAC local la capture
complète à un émetteur et contexte ; ce n’est pas une signature du fournisseur.
Les validateurs HTTP sont dans le cache, hors de cette attestation : leur simple
présence dans une archive à digest recalculable ne prouve pas leur association
à la représentation. `reuse_not_modified` est une primitive structurelle dont
le caller doit encore fournir la preuve de requête ; le moteur B4.4 refuse les
304 bruts. Le runner manuel prévalide les reprises avant les callbacks mais ne
recontrôle pas systématiquement la confiance au moment d’utiliser chaque cache.

## Choix additifs du lot, sans migration d’identité ou de stockage

1. Autorité locale explicite en mémoire, autorisations exactes source/contexte,
   révocation et rotation vers un nouvel alias de clé. Réutiliser un alias serait
   ambigu sans key_id dans B4 : interdit. Les anciens dictionnaires de clés restent
   compatibles pour les API historiques, sans nouvelles garanties de portée.
2. Liaison HTTP signée séparée, versionnée, du cache complet et URL exacte, donc
   des validateurs, révisions et contexte. Alternative refusée : modifier le
   manifeste B4 ou supposer qu’un digest non signé authentifie les validateurs.
   La liaison accompagne un descripteur de reprise ; aucune donnée historique
   n’est réécrite et aucun magasin de confiance global n’est installé.
3. Profil GET conditionnel strict sur transport injecté uniquement. Une URL,
   sélection, partition, représentation ou révision différente invalide la liaison.
   Métadonnées contradictoires ou non supportées : refus, pas de fallback caché.
4. Durée maximale locale explicite, mesurée depuis la capture B2 : après expiration,
   GET sans condition et réponse 200 requise. Alternative (304 renouvelant la
   fraîcheur via un nouveau registre de revalidations) différée : contrat/persistance
   distincts nécessaires. Un 304 ne change jamais la date, la provenance ou le
   snapshot, et ne prouve pas la fraîcheur de la révision distante.
5. Publication/reprise protégées par une vérification de la confiance courante.
   L’autorité locale est une dépendance de confiance, pas une preuve réseau/TLS.
   Les tests simulent l’origine du transport, sans appeler un fournisseur.

Étapes : reproduire les défauts → registre/validateurs → chemin 200/304 budgété
→ reprise/révocation/contradictions → suites complètes et checkpoint. Les garanties
sans environnement réel seront marquées TESTED hors ligne, pas VERIFIED fournisseur.

## Résultat de l'audit et corrections vérifiées

| Défaut reproductible | Correction additive / preuve |
|---|---|
| Validateurs modifiables dans un cache malgré une provenance B4 valide | Liaison HMAC séparée du cache complet et de l'URL ; le test démontre que `validate_cache` seul ne suffit pas, puis que `validate_binding` refuse l'altération |
| Reprise prévalidée avant révocation par un callback | Revalidation de chaque cache et événement complet ; deuxième publication refusée, fichiers précédents inchangés |
| Pas de portée source/contexte ou cycle de vie dans une simple table de clés | Registre explicite, alias/générations non réutilisables et grants exacts ; ancien mode table maintenu sans promesse supplémentaire |
| Possibilité de révoquer entre vérification et renommage | Verrou d'autorité tenu pendant la publication ; test à deux threads, puis reprise refusée après révocation |
| Validateurs syntaxiquement malformés acceptés par des tests superficiels | ETag unique opaque et Last-Modified canonique ; valeurs inconnues `null` conservées |
| Primitive 304 sans intégration transport/budget/expiration | API injectée distincte, conditions et liaison exactes, expiration contrôlée aussi pendant backoff/GET, jamais de nouvelle observation via 304 |

**644 tests OK**, dont 29 nouveaux ; les 615 précédents restent présents.
Les deux points d'entrée Discovery donnent les mêmes 391 cas uniques.
10 fixtures historiques, 135 fichiers privés et suffixe TODO depuis 3.1 inchangés
par SHA256. Les 19 fichiers de travail initiaux sont conservés ; seuls cinq sont
étendus pour ce lot (TODO, journal, manuel, provenance et couverture).

Durcissement explicitement incompatible avec les anciennes **valeurs malformées**
de validateurs, sans migration de format ou réécriture de fichier. Les formats
B2/B3/B4 et leurs références valides restent identiques. Voir
[le contrat livré et les décisions restantes](../../database/poc/PROVENANCE_HTTP_PHASE3.md).
Pas d'autorité durable ou distribuée, CLI protégée, collecte réelle ou preuve
fournisseur. Aucune des 34 cases composites n'est clôturée par simulation.
