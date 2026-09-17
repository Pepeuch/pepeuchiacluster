# Pepeuch AI Cluster

**Pepeuch AI Cluster** a pour objectif de rendre reproductible une architecture permettant de répartir des agents et modèles d'intelligence artificielle sur plusieurs machines en fonction des ressources disponibles.

Le but est d'exploiter au mieux le matériel déjà présent, sans nécessiter une seule machine très puissante.

Le système pourra notamment :

- répartir les tâches selon les capacités CPU, GPU, RAM et VRAM de chaque machine ;
- sélectionner le modèle ou l'agent adapté à chaque tâche ;
- utiliser des machines secondaires comme workers temporaires ;
- exploiter les ressources inutilisées lorsqu'elles sont disponibles ;
- charger et décharger dynamiquement les modèles selon les besoins ;
- exécuter des tâches interactives, planifiées ou en arrière-plan ;
- centraliser l'orchestration depuis un serveur principal ;
- permettre l'ajout de nouveaux modèles, agents et machines sans modifier l'architecture générale.

L'objectif est de construire une plateforme locale, modulaire et reproductible capable d'utiliser aussi bien de petits modèles spécialisés que des modèles plus lourds, en fonction du matériel disponible.

## Architecture prévue

```text
                       Client / Web UI
                              │
                              ▼
                    Orchestrateur central
                              │
                         Scheduler
                              │
                           Ray Head
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        Worker H24       Worker lourd     Worker léger
        GPU serveur       GPU puissant      GPU secondaire
              │               │               │
              └───────────────┼───────────────┘
                              │
                       Stockage central
```

Chaque agent ou modèle peut utiliser son propre environnement isolé, par exemple via Docker, avec les bibliothèques et runtimes dont il a besoin.

## État du projet

Le projet est actuellement en phase de conception et de prototypage.

La mise en place suivra une approche progressive :

1. serveur IA local ;
2. premier modèle et agent ;
3. système de jobs et scheduler ;
4. ajout des workers GPU ;
5. orchestration multi-agents ;
6. workflows spécialisés.

Voir [TODO.md](TODO.md) pour le plan de développement détaillé.

## License

Licensed under the Apache License, Version 2.0.

See the [LICENSE](LICENSE) file for details.