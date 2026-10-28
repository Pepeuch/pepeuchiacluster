# Checkpoint d’inventaire — reprise phases 0 à 3

28 octobre 2026. Branche créée : `feat/phases-0-3-integrity-cas` depuis
`5ead5754bd3424356eaf243bf6db271337a8faaa` ; main inchangée. Six commits
publiés vérifiés à distance et dans l’ascendance. Arbre initial propre, TODO
publiée avec sections futures conservée. Aucun commit/push/merge/rebase.

Les 35 lignes sont classées dans [la matrice de reprise](PHASES_0_3_CLASSIFICATION_20261028.md).
Aucune case encore cochée. Baseline TODO SHA256 :
`a361d4f6df798aeb44e1989fd9d816ce1cf70a012410ae79024431f43dbcfb60`.
116 fichiers privés inventoriés sans exporter leur contenu, aucun modifié.
Les anciens checkpoints et résultats restent les preuves historiques.

Lecture terminée du checkpoint de reprise et de la couverture. Défauts repérés
à confirmer par tests : date B2 absente acceptée, égalité Python false/0 dans
les scopes, égalité de dates/représentations dans le plan, préconditions CAS
encore uniquement simulées. Priorité : corriger les entrées invalides sans
changer les sorties valides, puis ajouter un chemin CAS explicite sans exécution
automatique. Aucun moteur réel, restauration, accès VM/Proxmox ou système modifié.
Les nouvelles validations et fichiers seront consignés dans un checkpoint suivant.

## Étape locale intégrité et CAS

Les tests initiaux ont reproduit date absente/nulle acceptée, SQL partiel
sur KeyError, champ d’enveloppe non lié, scopes false/0 assimilés et manifeste
HMAC dont le scope peut être altéré false→0. Corrigés sans changer les sorties
valides. Transition commune : instants exacts et fuseaux équivalents acceptés,
pas de classement lexical des révisions. CAS opt-in par snapshot attendu,
absence attendue explicite et rejeu déjà appliqué ; provenance contrôlée requise
dans l’API de transition protégée, comptes privés refusés.

Tests ciblés : 44 succès ; suite Discovery : 360 succès (347 + 13 nouveaux).
Toutes les fixtures/références et les 116 exports privés sont inchangés ; la TODO
reste exactement celle publiée. Qualification réelle CAS préparée via --cas-only :
aucune restauration, aucun benchmark, seulement nouvelles bases synthétiques.
La concurrence PG/SurrealDB n’est PAS encore validée à cette étape.
