# Banc B5.3.1 — future VM jetable uniquement

**Aucun test OS de ce banc, préparateur root ou contrôleur root n'a été exécuté
dans la mission.** Les tests ordinaires vérifient les règles avec des fixtures et
des appels simulés. Une paire de sockets Unix privée a servi à vérifier les
credentials IPC de l'utilisateur courant, sans listener/root ni preuve de sandbox.

Le banc est extérieur au worker : aucune nouvelle capacité, outil ou commande
n'est exposée au texte des missions. Il n'est pas lancé par unittest discover.
Ses résultats ont toujours `verified: false`, un état candidat/inconclusif ou FAIL,
et un code de sortie 2. Ils ne constituent pas un permis strict.

## Périmètre et garde-fous

`isolation-pilot/v1` contient seulement un run ID, une racine synthétique neuve,
UID/GID non root attendus, deux ports locaux distincts, des pairs contrôlés privés
IPv4 RFC1918/IPv6 ULA et une fenêtre monotone de 600 s maximum liée au boot ID.
Pas de DNS, URL, Internet, texte de commande ou chemin de secret réel. Exemples
publics dans `deploy/worker-linux/` : **sentinelles invalides/périmées à remplacer**,
pas des données de déploiement.

La racine est exactement `/opt/pepeuch-b531-fixtures-<run_id>` ou
`/var/lib/pepeuch-b531-fixtures-<run_id>`. `prepare` exige root et le flag de pilote
explicite ; il refuse une destination existante, ne répare ni ne nettoie rien.
Il crée exclusivement des canaris à contenu public connu, un marqueur root 0444,
des dossiers de faux backend privés et un livrable synthétique. Le canari hôte
`host-write.canary` est volontairement **0666** pour distinguer la protection de
montage de la DAC ; cette permission ne concerne que ce fichier neuf et nécessite
la revue/autorisation opérateur. Aucun vrai secret, index ou workspace n'est copié.

```
<fixture_root>/PILOT_SCOPE.json       # hors du faux backend masqué
<fixture_root>/backend/secrets/admin.canary
<fixture_root>/backend/app/index.canary
<fixture_root>/backend/workspaces/forbidden.canary
<fixture_root>/host-write.canary
<fixture_root>/published/result.canary
```

Pour la sonde filesystem, `InaccessiblePaths` cible le **faux backend** ci-dessus,
pas la racine contenant le marqueur. Les refus de ses canaris ne prouvent pas à eux
seuls la sécurité d'un backend réel : l'opérateur doit corréler comptes, modes,
montages et profil final. Le parcours API utilise lui aussi un backend neuf de
test ; aucune donnée de la VM historique ne doit être utilisée.

## Ordre du futur pilote, après autorisation distincte

1. Inventorier les versions, comptes/groupes, unités, cgroups, chemins et règles
   existants en lecture seule. Confirmer machine jetable, UID exclusif, absence de
   conflits et propriété des deux pairs réseau. Relever les SHA du code/profil.
2. Rendre une copie publique du scope, remplacer boot ID, run ID, temps monotones,
   UID/GID et endpoints approuvés ; `plan` ne fait aucune opération réseau.
3. Faire approuver la création des seuls canaris root et des comptes/répertoires
   nouveaux. Créer les fixtures, puis vérifier leur existence/mode/SHA depuis
   l'extérieur de la sandbox. Ne pas afficher de vrai credential.
4. Faire approuver séparément le profil systemd et, si nécessaire, la table nftables
   de test par UID. Ne jamais fusionner/vider/remplacer le pare-feu existant. Vérifier
   que le compte ne porte aucun autre service et qu'aucun socket IPv4 d'un autre UID
   n'est hérité. Les compteurs de filtrage sont à relever par l'opérateur externe.
5. Lancer chaque cas fixe dans une unité de sonde relue reprenant les protections
   et limites, sous l'UID worker. Une simple commande `sudo -u` ne teste pas systemd.
6. Pour les cas de cycle de vie, vérifier les limites **avant** toute création de
   l'unique enfant ; superviser de l'extérieur PID/starttime/cgroup. Stopper seulement
   cette unité et relever parent/enfant/cgroup après arrêt. Durée et disparition
   exigent un témoin indépendant, pas la sortie du processus que l'on tue.
7. Arrêter les seules unités de test, vérifier leurs cgroups vides, révoquer la clé
   worker de test et conserver les livrables. Faire approuver le retrait des seuls
   fichiers/règles créés et comparés. Pas de nettoyage récursif/global automatique.

Exemples **à adapter uniquement après ces confirmations**, non exécutés ici :

```bash
python3 -m pilot.worker_isolation plan --scope-file /chemin/revu/scope.json
sudo python3 -m pilot.worker_isolation prepare --scope-file /chemin/revu/scope.json --authorized-disposable-pilot
# Dans l'unité candidate, avec son UID, son code immuable et le marqueur créé :
python3 -m pilot.worker_isolation probe --scope-file /opt/pepeuch-b531-fixtures-RUN_ID/PILOT_SCOPE.json --case secret --authorized-disposable-pilot
```

`RUN_ID` est à remplacer par les 32 caractères hexadécimaux du scope. Les flags
sont des barrières aux lancements accidentels, **pas une autorisation utilisateur
implicite** ni une preuve d'isolation. Ne pas exécuter `prepare`, les sondes ou le
contrôleur privilégié sur la machine de développement ou la VM existante.

## Cas disponibles et interprétation

| Cas | Action fixe et borne | Interprétation |
|---|---|---|
| `secret`, `sqlite`, `workspace` | Ouvrir le canari connu, puis fermer sans lire un octet | EACCES/EPERM seulement candidat ; ENOENT est inconclusif |
| `outside_write` | O_WRONLY sans O_CREAT/O_TRUNC/écriture sur le seul canari public | EROFS/EACCES/EPERM candidat ; accès réussi = FAIL, contenu conservé |
| `docker`, `gpu` | Métadonnées seulement, aucune ouverture GPU ni connexion Docker | NOT VERIFIED sans inventaire hôte/namespace/DevicePolicy externe |
| `backend_connect` | TCP local, 300 ms, aucune donnée/clé envoyée | Joignabilité candidate, pas validation de l'identité ou du rôle API |
| `other_loopback` | Autre port contrôlé du même loopback | Réussite = FAIL ; refus de service/timeout ne prouvent pas le filtre |
| `controlled_peer`, `ipv6` | Littéraux privés approuvés, 300 ms, aucun octet envoyé | EACCES/EPERM candidat ; corrélation noyau/compteurs indispensable |
| `resources` | Lectures de cgroup v2 et contexte | Valeurs effectives, pas charge CPU/RAM/PID ni validation de sandbox |
| `child_stop` | Un enfant Python fixe, 8 s ; parent attend au plus 10 s | Témoin externe requis ; fallback nettoie uniquement son propre enfant |
| `expiration` | Attente fixe 60 s, sans charge | RuntimeMax attendu 55 s, superviseur externe ; retour seul n'est pas succès |
| `results_preserved` | SHA du seul livrable synthétique connu | Préservation candidate ; les vrais résultats API restent couverts par les tests applicatifs |

Les deux cas de cycle de vie refusent d'abord privilèges/cgroups incomplets,
limites illimitées, mémoire/PID/CPU excessifs ou swap non nul. Aucune fork bomb,
allocation de saturation ou charge globale n'est implémentée.

## Contrôleur de diagnostic, toujours deny

`python3 -m pilot.worker_isolation.controller` est une proposition **root temporaire**,
non exécutée. Il exige root/groupe root et le flag de pilote, crée un chemin neuf
`/run/pepeuch-b531-verifier-<run_id>/verifier.sock`, attend 20 s une seule connexion,
contrôle les messages bornés et répond `deny`. Le nettoyage compare les inodes
créés et préserve toute entrée inattendue ; aucun service permanent ni installation.

Le drop-in `verifier-fd.conf.in` propose que PID1 fournisse cette connexion au
worker par `OpenFile`, sans élargir ses familles de sockets. Il est lui aussi non
installé. Le FD 3 n'est valable qu'après inventaire des FD de cette nouvelle unité.
**Un contrôleur root diagnostique et une série de sorties worker ne constituent pas
encore une chaîne indépendante d'attestation** ; le producteur de permis reste
absent tant que les preuves OS et leur collecte n'ont pas été qualifiées.
