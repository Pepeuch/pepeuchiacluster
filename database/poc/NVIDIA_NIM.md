# Lot B1.1 — NVIDIA NIM Metadata API, sans GPU ni clé

## Périmètre

NVIDIA a publié une **NIM Metadata API v1.0.0**, lisible sans compte, clé ni
GPU. Elle décrit des *microservices NIM* par `resourceId` et `tag` de conteneur.
Elle n'est **pas** un catalogue de modèles HF, ne garantit pas l'accès au
registre NGC et n'affirme pas qu'une configuration a été exécutée avec succès.

Sources officielles :

- [Prérequis et droits](https://docs.nvidia.com/nim/metadata-api/1.0.0/get-started/prerequisites)
- [Endpoint GET](https://docs.nvidia.com/nim/metadata-api/1.0.0/reference/endpoints)
- [Champs de réponse](https://docs.nvidia.com/nim/metadata-api/1.0.0/reference/response-fields)
- [Choisir un profil matériel](https://docs.nvidia.com/nim/metadata-api/1.0.0/guides/choose-a-profile)
- [Limites et couvertures](https://docs.nvidia.com/nim/metadata-api/1.0.0/reference/limitations)

## Distinction des accès (compte NVIDIA Developer existant)

| Fonction | Authentification | Portée de B1.1 |
| --- | --- | --- |
| Lecture `GET /v2/nim/metadata` | **Aucune** | Oui, lecture réelle |
| API de modèles hébergés sur `build.nvidia.com` | Clé développeur/API, compte éligible | Non, ultérieur |
| Conteneurs et modèles du registre `nvcr.io` / NGC | Clé NGC et droits/entitlements adaptés | Non, ultérieur |
| Exploitation locale avec accélération NVIDIA | Matériel, pilote, conditions d'utilisation | Non, VM sans passthrough |

La [documentation NVIDIA pour le programme Developer](https://docs.api.nvidia.com/nim/docs/run-anywhere)
décrit un accès de prototypage aux endpoints et des possibilités de NIM
téléchargeables à des fins de recherche et développement. Cela **n'accorde
pas automatiquement** accès à tous les artefacts, et l'usage en production
est soumis à d'autres conditions.

**Sécurité future** : créer seulement les clés nécessaires, leur donner les
permissions les plus faibles possibles, les conserver hors du dépôt et des
rapports (`/opt/pepeuch-ai/config/` avec permissions restrictives), ne jamais
les afficher dans le terminal partagé ou dans les logs. Aucune clé n'est
nécessaire pour exécuter la sonde de ce lot.

## Commandes

Depuis la racine du repo, sur la VM Debian :

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -v
python3 database/poc/probe_source_adapters.py --nim-only
```

La sonde utilise par défaut l'exemple publié par NVIDIA :
`nim/nvidia/parakeet-1-1b-rnnt-multilingual`, tag `1.5.0`.
Pour tester **un autre tag effectivement présent dans NGC** :

```bash
python3 database/poc/probe_source_adapters.py \
  --nim-only \
  --nim-resource-id nim/nvidia/parakeet-1-1b-rnnt-multilingual \
  --nim-tag 1.5.0
```

Le statut HTTP 404 devient `metadata_status=unavailable_for_tag` ; les autres
erreurs HTTP restent visibles. Les réponses sont plafonnées à 3 Mo, les requêtes
ont un timeout de 20 s par défaut, et seules les statistiques sont affichées.
Le `tag` peut changer : ce n'est ni un SHA Git ni un digest OCI immuable.

## Matériel cible, **pas encore disponible dans la VM**

| Champ | Valeur physique connue |
| --- | --- |
| Carte | NVIDIA RTX A2000 12 Go |
| GPU PCI `lspci` | `10de:2571` (vendor:device) |
| Format requis par l'API NIM | `2571:10de` (device:vendor) |
| Mémoire vidéo | 12 Go par GPU |
| GPU physiques dédiés envisageables | 1 |
| Pilote dans Debian, accès VFIO/PCI passthrough | Non validés |

**Critères de sélection conservateurs** :

1. Correspondance `gpu_device` directe, présence dans `tested_gpu_devices`, ou
   aucun GPU cible déclaré (GPU-agnostic). Les champs `gpu`/`gpu_device`
   acceptent déjà une chaîne ou une liste, comme prévu par NVIDIA.
2. Si la VRAM minimale publiée dépasse 12 Go, exclusion ; si le champ est
   absent, verdict `candidate_unverified`.
3. `tensor_parallel_size × pipeline_parallel_size` doit tenir sur **un** GPU.
4. Les exigences CPU, RAM hôte, disque et pilote publiées, si présentes,
   restent `not_checked` jusqu'à mesure dédiée. Le mode `gpu_agnostic` ne veut
   pas dire « testé sur RTX A2000 ».
5. `runtime_verified` reste **toujours `false`** à ce stade, y compris pour une
   candidature respectant tous les critères enregistrés.

## Observation réelle du 27 octobre 2026

Endpoint public exact :

```
GET https://api.ngc.nvidia.com/v2/nim/metadata?resourceId=nim/nvidia/parakeet-1-1b-rnnt-multilingual&tag=1.5.0
```

Réponse HTTP 200 ; 60 profils :

| Résultat du *screening* théorique A2000 | Nombre |
| --- | ---: |
| Profils ciblant explicitement d'autres GPU | 48 |
| Profils GPU-agnostic, candidats non vérifiés | 12 |
| Profils avec VRAM minimale renseignée | **0** |
| Profils validés en exécution dans la VM | **0** |

Par ailleurs `tool_calling` et `vgpu_support` sont **absents** de cette réponse,
ce qui n'équivaudra jamais à `false` en base. Pour les 60 profils,
`tested_gpu_devices` est explicitement `[]` ; cela ne signifie pas qu'aucune
carte ne peut les utiliser.

Ce POC ne tente pas de connexion NGC, ne tire aucun conteneur et n'active aucun
pilote. Pour une décision d'installation, il faudra aussi vérifier le driver,
le passthrough, le support d'architecture et la licence/entitlement.
