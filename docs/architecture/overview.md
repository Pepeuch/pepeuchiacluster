# Schéma global de l’architecture

## Version Mermaid

```mermaid
flowchart TD

    U[M6800 / Client principal\nNavigateur Web • SSH • Git]

    subgraph P[Serveur Proxmox]
        subgraph VM[VM IA centrale]
            O[Orchestrateur\nOrca]
            S[Scheduler\nJobs • Priorités • Planification]
            R[Ray Head\nRépartition des tâches]
            DB[(PostgreSQL / Qdrant)]
            UI[Open WebUI / API]
            AG[Agents H24\nFichiers • Docs • Infra]
        end

        A2000[A2000 12 Go\nWorker H24]
        ST[(Stockage central\nFichiers • Modèles • Logs • Résultats)]
    end

    subgraph W1[Station de travail]
        SSD1[SSD USB3 AI Node]
        N1[Worker lourd\nRTX 5060 Ti 16 Go]
        M1[Gros modèles\nVision • Code • PCB lourd]
    end

    subgraph W2[NUC9]
        SSD2[SSD USB3 AI Node]
        N2[Worker léger\nRTX 4060 8 Go]
        M2[Petits modèles\nEmbeddings • Classification]
    end

    subgraph OPT[Extensions futures]
        HA[Home Assistant]
        FRI[Frigate]
        HAI[Hailo-8]
        MQTT[MQTT / API]
    end

    U --> UI
    UI --> O
    O --> S
    S --> R
    O --> DB
    O --> AG
    DB --> ST
    AG --> ST

    R --> A2000
    R --> N1
    R --> N2

    A2000 --> ST
    N1 --> ST
    N2 --> ST

    SSD1 --> N1
    SSD2 --> N2
    N1 --> M1
    N2 --> M2

    FRI --> HAI
    FRI --> MQTT
    HA --> MQTT
    O --> MQTT
```

## Version texte simple

```text
                           ┌──────────────────────────────┐
                           │       M6800 / Client         │
                           │    Web UI • SSH • Git        │
                           └──────────────┬───────────────┘
                                          │
                                          ▼
                    ┌────────────────────────────────────────────┐
                    │            Serveur Proxmox                 │
                    │                                            │
                    │  ┌──────────────────────────────────────┐  │
                    │  │            VM IA centrale            │  │
                    │  │                                      │  │
                    │  │  Orca / Orchestrateur               │  │
                    │  │  Scheduler / Jobs / Priorités       │  │
                    │  │  Ray Head                           │  │
                    │  │  Open WebUI / API                   │  │
                    │  │  PostgreSQL / Qdrant                │  │
                    │  │  Agents H24                         │  │
                    │  └──────────────────────────────────────┘  │
                    │                    │                        │
                    │                    ▼                        │
                    │          A2000 12 Go / Worker H24          │
                    │                    │                        │
                    │                    ▼                        │
                    │    Stockage central : fichiers / modèles   │
                    │       logs / jobs / résultats / index      │
                    └───────────────┬─────────────────────┬───────┘
                                    │                     │
                                    │                     │
                                    ▼                     ▼
                    ┌────────────────────────┐   ┌────────────────────────┐
                    │   Station de travail   │   │          NUC9          │
                    │  SSD USB3 AI Node      │   │   SSD USB3 AI Node     │
                    │  RTX 5060 Ti 16 Go     │   │   RTX 4060 8 Go        │
                    │  Worker lourd          │   │   Worker léger         │
                    │  Gros modèles          │   │   Petits modèles       │
                    └────────────────────────┘   └────────────────────────┘

Extensions futures :
Frigate → Hailo-8 → MQTT/API → Orchestrateur
Home Assistant → MQTT/API → Orchestrateur
```

## Lecture rapide

- **M6800** : poste de pilotage.
- **Serveur Proxmox** : cœur du système.
- **VM IA** : orchestration, scheduling, base de données, API, agents permanents.
- **A2000** : worker H24 pour les tâches permanentes et légères/moyennes.
- **Station 5060 Ti** : worker lourd à la demande.
- **NUC9 4060** : worker léger pour tâches parallèles.
- **Stockage central** : source unique des fichiers, modèles, logs et résultats.
- **Frigate / Hailo / Home Assistant** : extensions futures via MQTT/API.
