# Plan documentaire après audit des phases 0–3

28 octobre 2026. Proposition à examiner, aucun About GitHub modifié.

Description About proposée : « Plateforme IA locale et hybride : découverte de
ressources multi-sources, catalogue personnel et orchestration de workers sous
approbation humaine. Prototype expérimental. » Ne pas annoncer un worker GPU
sécurisé, scheduler ou cluster distribué déjà opérationnel.

Le README doit rendre visibles, dans cet ordre : objectif et chaîne d’architecture,
matrice disponible/préparé/non vérifié, lancement local CPU sans modèle, commandes
de tests, limites réseau/OS, liens vers roadmap et décisions. Conserver les
commandes B5.1–B5.3 compatibles. Ajouter le checkpoint B5.3.1 et l’état actuel
des bases à côté des preuves historiques ; une base arrêtée n’annule pas un test
passé et un GPU disponible n’établit pas une inférence opérationnelle.

| Sujet | Présentation à adopter |
|---|---|
| Discovery | Sept adaptateurs/fixtures et primitives B4 testés ; ingestion distante/planification production non validées |
| Ressources | Référence modèle, artefact, agent, microservice et endpoint distincts ; catalogue accessible ≠ inférence accessible |
| Catalogue personnel | Séparé du Discovery Cache, décision humaine ; pas de fusion interplateforme |
| Control Plane | Python/SQLite, missions/livrables durables, local/loopback ; HTTP production et TLS/appairage ouverts |
| Worker | CPU SHA256 borné, sans IA ; mode strict refuse tant que preuve OS indépendante absente |
| Infrastructure | GPU VM150 confirmé, CUDA Debian rapporté, visibilité Docker rapportée ; calcul Docker/inférence/stress non vérifiés |
| Bases | POC historiques préservés et arrêtés ; banc synthétique 30/1k/10k vérifié, choix et exploitation encore ouverts |

`docs/architecture/overview.md` et le quickstart conservent des cibles
Orca/Ray/Qdrant/UI anciennes, désormais explicitement marquées historiques.
Un schéma de l’état réel et un lien d’audit ont été ajoutés dans ce lot.
La réécriture complète reste un lot dédié après validation des décisions. Ne pas installer
leur stack pour rendre une ancienne illustration « vraie ». Vérifier les liens,
les versions et la procédure de démo, sans modifier les chapitres TODO 3.1+.

Les choix encore nécessaires sont des décisions distinctes : moteur principal,
comptes/domaines et révisions Discovery, packaging/TLS production, émetteur de
permis indépendant, machines pour matrice multi-OS et environnement jetable
Proxmox/OS. Une réécriture documentaire ne peut les valider à leur place.
