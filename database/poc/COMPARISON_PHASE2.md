# Comparatif PostgreSQL / SurrealDB — état et décision conditionnelle

28 octobre 2026. Banc synthétique **VERIFIED** sur 30/1 000/10 000 modèles ;
choix du moteur principal **PARTIAL / BLOCKED** par la revue des résultats et
du périmètre d’exploitation. Aucun POC historique, schéma ou volume existant
modifié. Pas de décision de migration. [Mesures, méthode et limites réelles](ISOLATED_DOCKER_BENCH.md).

## Preuves disponibles

Les POC historiques ont conservé 405 modèles et ont fait l’objet de comparaisons
fonctionnelles et de sauvegardes/restaurations rapportées. Les 14 requêtes de
`benchmark_readonly.py` servent la parité ; leur temps incluant lancement Docker
et CLI ne constitue pas un benchmark moteur. Voir [QUERY_PARITY.md](QUERY_PARITY.md).

Lecture réelle VM150 le 28/10 : les deux conteneurs existent, **arrêtés** avec
code 0, état health enregistré `unhealthy`. Ceci ne diagnostique pas la cause
ni ne contredit leurs preuves historiques ; aucun démarrage n’a été tenté.
Leurs montages persistants sont présents et aucun plafond Docker CPU/RAM n’est
configuré (`Memory=0`, `NanoCpus=0`). Ces deux POC restent hors des essais ; deux
nouveaux conteneurs ont ensuite été autorisés et mesurés avec plafonds identiques.
Des exports historiques PostgreSQL et SurrealDB
existent dans `backups` ; présence/taille ne prouvent pas leur restauration.
Les cinq dernières sondes conservées ont code 0 pour chaque moteur avant l’arrêt :
readiness historique confirmée. Les réseaux sont internes, sans ports publiés ;
la politique de redémarrage observée est `no`. Les journaux filtrés montrent des
marqueurs d’arrêt, pas une cause établie. [Relevé complet sans secrets](../../docs/infrastructure/VM150_READONLY_20261028.md).
L’utilisateur a confirmé de conserver les deux bases arrêtées ; aucun accès
supplémentaire à Proxmox n’est autorisé.

| Critère | PostgreSQL | SurrealDB | Conclusion actuelle |
|---|---|---|---|
| Catalogue tabulaire / filtres | POC et parité historique | POC et parité historique | Parité fonctionnelle ; adoption ouverte |
| Modèle → variante → runtime/GPU | Jointures vérifiées | Liens natifs vérifiés | VERIFIED sur corpus synthétique |
| Liens typés / graphe | Requêtes et plans avant/après index | Relations typées, requêtes et plans validés | VERIFIED sur les parcours testés |
| Vecteurs / hybride | Scan cosinus exact 16 dimensions | Même baseline et ordre de résultats | VERIFIED exact ; ANN/non synthétique NOT VERIFIED |
| CPU/RAM / index / charge | Cgroups CPU/mémoire/PID et plans mesurés | Même protocole, limites identiques | VERIFIED, série bornée à faible concurrence |
| Import / mise à jour | Rollback, déconnexion et lots confirmés vérifiés | `/import` partiel 422, transactions/lots/reprise vérifiés | Legacy rejoue un ancien état sans garde d’ordre |
| Sauvegarde / restauration | 4 nouvelles destinations vérifiées | 4 nouvelles destinations vérifiées | Ne prouve pas backup/restauration VM150 |
| Licence moteur | PostgreSQL License | BSL 1.1 au tag exact étudié | Condition d’exploitation distincte |

## Licence et artefact exact

La PostgreSQL License permet usage, modification et redistribution sous réserve
de ses notices. [Texte officiel](https://www.postgresql.org/about/licence/).
Le tag `postgres:16-alpine` du Compose reste flottant : relever version mineure
et digest dans chaque mesure, sans actualiser implicitement le POC.

Le fichier du **tag `v3.3.4`** SurrealDB est BSL 1.1. Il porte le libellé de
travail « SurrealDB 3.0 » et prévoit Apache-2.0 à la date du 1er janvier 2030,
ou selon la règle de conversion du texte. L’autorisation additionnelle exclut
certains services de base de données où des tiers peuvent administrer schémas
ou tables ; les employés et prestataires directs sont distingués. Ce texte
n’équivaut pas à une autorisation SaaS universelle. Le statut des SDK ne tranche
pas celui du moteur. [Licence exacte du tag](https://raw.githubusercontent.com/surrealdb/surrealdb/v3.3.4/LICENSE).

Ces constats sont vérifiés sur les sources officielles, pas une approbation
juridique de tous les usages futurs. Avant adoption : décrire utilisateurs,
droits exposés et redistribution, confirmer les notices de l’image effective.
La VM expose le digest SurrealDB
`sha256:649a60a3b9c0177d9923c938e1c2563e48cde2a9d06ac2c0519714be719b02af` ;
son contenu LICENSE n’a pas été extrait. Aucun paiement ou licence commerciale
n’a été engagé. La case de décision globale reste ouverte.

## Contrat de charge reproductible ajouté

`comparison_workload.py` sans argument imprime un corpus explicitement synthétique
et son SHA256, avec état BLOCKED pour les mesures. Aucune connexion ou installation.
La fixture `comparison.synthetic.json` contient modèles, variantes, fournisseurs,
runtimes, GPU, liens `supports`/`fits`, vecteurs et cinq résultats littéraux.
Les tests recalculent indépendamment relations, cosinus et score hybride.

| Requête | Sémantique commune / ordre de normalisation |
|---|---|
| `provider_models` | Modèles du fournisseur p1, identifiants triés |
| `cpu_variants` | Variantes ≤12 Go reliées à r1 par `supports`, identifiants triés |
| `typed_gpu_paths` | Intersection `fits` vers g1 et `supports` vers r2, modèles distincts triés |
| `vector_exact` | Cosinus exact pour [1,0], top 3 décroissant, égalités par ID |
| `hybrid_exact` | 0,75 × cosinus + 0,25 × présence littérale de `chat` dans le nom, même ordre |

Arrondir les scores à huit décimales, sérialiser comme nombres flottants, conserver
les identifiants. L’hybride est une baseline explicite, pas BM25 ; deux dimensions
et trois modèles ne qualifient aucune recherche sémantique ou index ANN. Les
traductions SQL/SurrealQL et le runner du banc à huit requêtes sont désormais
implémentés et validés dans l’environnement approuvé. Ce prototype à cinq
requêtes et son validateur restent distincts, sans changement de leur contrat.

Méthode appliquée : mêmes corpus et cardinalités 30/1k/10k,
seed figée, mêmes plafonds CPU/RAM et hôte, concurrence unitaire,
une session persistante par moteur, mesures warm ; cold OS non testé. Versions,
digests, index, plans, latences client, p50/p95 et cgroups CPU/mémoire sont consignés.
Le coût d’import initial et les mises à jour/reprises sont mesurés séparément.
Les métriques des exécutions profilées restent distinctes des latences normales.
Pour ANN, mesurer
aussi rappel contre la baseline exacte ; ne pas confondre index vectoriel et
scan exact sans extension. Conserver les résultats bruts hors secrets.

Le validateur exige toutes les requêtes, ≥10 échantillons par requête, plans,
plafonds/mesures CPU/RAM, preuves déclarées d’import et restauration. Il rejette
les temps `docker_exec`, profils différents, résultats divergents et métriques
non finies. Il calcule p50/p95 sans choisir le moteur. Des rapports fournis par
un opérateur ne sont pas attestés : leurs preuves et conditions restent à auditer.
Les nombres du test de ce validateur à cinq requêtes sont simulés ; les mesures
et fixtures observées du banc distinct sont explicitement identifiées comme telles.

## Plan initial, autorisé puis exécuté

Autorisation utilisateur reçue : environnement de test distinct des POC historiques,
deux conteneurs nommés avec identifiant de campagne, images figées par digest,
aucun port LAN ni montage historique, réseau fermé et ressources identiques.
Pas de téléchargement d’image. Bases et données synthétiques réservées
à la campagne ; backup/restore uniquement vers une cible nouvelle. Échecs injectés
sur lots, transaction avant COMMIT, déconnexion et préfixe `/import`, puis rejeu
et comparaison de contenu, y compris ressources non observées. Pas d’exhaustivité
revendiquée pour tous les instants de panne physique ou d’interruption réseau.

Hôte, images, plafonds, stockage temporaire et méthode de connexion sont consignés
dans le rapport du banc. Fin d’essai : seuls les nouveaux conteneurs sont arrêtés ;
rapports et exports conservés. Aucun
prune, nettoyage global, suppression de volume ou remplacement de base historique.
Le démarrage des POC existants pour un healthcheck est une autre autorisation,
qui n’autorise ni création de tables de benchmark ni test d’interruption dessus.

Recommandation conditionnelle : conserver les deux POC et l’ADR de choix ouvert.
Les mesures API de cette charge favorisent PostgreSQL comme candidat de départ.
Les plans sont des exécutions profilées distinctes et ne doivent pas être mélangés
aux latences client ; aucun classement universel du moteur n’est conclu. SurrealDB
reste à considérer pour d’autres parcours/optimisations de graphe et sous ses
conditions d’usage. Choix principal et licence d’exploitation attendent validation.
