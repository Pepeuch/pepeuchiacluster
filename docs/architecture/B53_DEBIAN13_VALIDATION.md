# B5.3 — protocole manuel Debian 13, non exécuté

**Mise à jour B5.3.1 — 28 octobre 2026** : [audit et risques](B531_SECURITY_AUDIT.md),
[contrat de vérification](ISOLATION_VERIFICATION_B531.md) et
[banc séparé](../../pilot/worker_isolation/README.md). Le diagnostic Linux, le canal
hérité et les contrôles de fraîcheur sont implémentés ; le contrôleur proposé
émet toujours `deny`. Aucun producteur qualifié de permis positif n'est livré,
aucune sonde OS ou opération root de ce guide n'a été exécutée. Les comptes,
VM, unités et règles existants restent inchangés.

Cette procédure vise **une machine de test distincte explicitement autorisée**.
Elle n'autorise aucune intervention sur la VM actuelle, Proxmox, HAOS, NAS,
Docker, GPU, bases POC ou données historiques. Les commandes privilégiées ci-dessous
sont proposées pour examen ; aucune n'a été exécutée pendant cette mission.

Le worker CPU et l'API fonctionnent en test applicatif. **Le mode strict reste
bloqué** : l'inspecteur ne possède pas encore les preuves OS obligatoires. Ce guide
permet de préparer puis vérifier un profil candidat ; il ne promet pas un service
sécurisé déployable immédiatement. Les tests OS ci-dessous sont `NOT VERIFIED`.

## 1. Préparer le périmètre et les versions

Faire approuver au préalable : compte/groupe worker dédiés, répertoires de code,
état et credential nouveaux, unité de test, canaris synthétiques et éventuel pair
réseau de test contrôlé. Ne pas installer de paquet ou modifier un pare-feu pour
faire passer un essai sans autorisation supplémentaire. Conserver les autres
services et les fichiers existants ; refuser toute destination déjà utilisée.

Relever sans installation :

```bash
cat /etc/os-release
uname -r
python3 --version
python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'
systemd --version
stat -fc %T /sys/fs/cgroup
cat /sys/fs/cgroup/cgroup.controllers
git branch --show-current
git rev-parse HEAD
git status --short
```

Cible étudiée : Debian 13/trixie, famille systemd 257, cgroup v2 avec contrôleurs
`cpu memory pids` réellement disponibles. Les options proviennent des manpages
Debian [systemd.exec](https://manpages.debian.org/trixie/systemd/systemd.exec.5.en.html),
[resource-control](https://manpages.debian.org/trixie/systemd/systemd.resource-control.5.en.html)
et [service](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html).
`LoadCredential` expose un fichier privé en lecture seule ; ne pas employer
`SetCredential` pour une valeur secrète. Les filtres IP peuvent être sans effet
si le noyau/délégateur ne prend pas en charge l'eBPF cgroup : vérifier par essais.
`RuntimeMaxSec` est utilisé avec `Type=exec`, pas `oneshot`.

Dans l'environnement de développement uniquement, syntaxe du gabarit acceptée
par `systemd-analyze verify --man=no --generators=no` sous systemd 255.4 Ubuntu.
Cela ne valide ni Debian 13, ni le chargement des restrictions, ni leur efficacité.
La validation Debian 13 B5.2 rapportée par l'utilisateur (395 tests, Python 3.13.5,
SQLite 3.46.1, sauvegarde/restauration) n'est pas une validation OS B5.3.

## 2. Installation proposée, seulement après autorisation

Choisir des chemins absolus neufs, sans espaces, `%` ni liens symboliques. Exemple
de périmètre jetable, **à adapter et vérifier avant toute commande** :

| Paramètre | Exemple proposé |
|---|---|
| Code immuable pour le worker | `/opt/pepeuch-worker-b53-test` |
| Parent d'état privé worker | `/var/lib/pepeuch-worker-b53-test` |
| Racine donnée à `--worker-dir` | `/var/lib/pepeuch-worker-b53-test/instance` (inexistante avant `init`) |
| Backend de test, UID différent non root | `/var/lib/pepeuch-b53-test-backend` |
| Source credential, propriétaire root | `/etc/pepeuch-worker-b53-test/worker.token` |
| Unité de test | `pepeuch-worker-b53-test.service` |

Le backend de test doit déjà être initialisé par son opérateur sous son compte
distinct. Ne jamais utiliser ni changer les permissions du backend existant de la
VM. Vérifier son propriétaire et son mode privé, ainsi que tous les parents :
`stat`, `namei -l`, `id <compte-backend>`. Comparer ensuite UID et groupes du worker.

Création proposée du seul compte worker, si aucun compte dédié n'existe :

```bash
sudo groupadd --system pepeuch-b53-worker
sudo useradd --system --gid pepeuch-b53-worker --no-create-home \
  --home-dir /nonexistent --shell /usr/sbin/nologin pepeuch-b53-worker
id pepeuch-b53-worker
```

Ne pas ajouter ce compte aux groupes backend, sudo, docker, video, render ou disk.
L'exclusivité de son usage fait partie de la revue opérateur. Le compte `nobody`
et les UID/GID du fichier d'exemple ne sont pas des identités de déploiement.

Copier une version B5.3 relue de **`control_plane/` et `pepeuch_worker/`** vers le
nouveau répertoire de code, sans données backend, `.git`, secret ni dépendance
externe. Propriétaire administrateur, fichiers lisibles/exécutables seulement selon
leur besoin, aucun droit d'écriture pour le worker ; parents traversables. Pas de
pip, Docker, environnement CUDA ou moteur IA nécessaire.

Créer le parent d'état neuf en 0700 appartenant au worker ; laisser `instance`
inexistant. Créer le répertoire de credentials root en 0700. Ces changements
doivent être limités aux chemins approuvés ; aucun `chmod/chown -R` d'un répertoire
historique. Préparer dans le répertoire de code un JSON public 0644 depuis
`deploy/worker-linux/worker-config.example.json`, remplacer ID, port, UID/GID et UID
backend. Le JSON ne doit contenir aucun credential, clé admin ou `verified: true`.

Backend arrêté et worker arrêté, l'opérateur backend enrôle explicitement :

```bash
python3 -m control_plane worker-enroll --data-dir /var/lib/pepeuch-b53-test-backend \
  --capability cpu.text.sha256.v1 --lease-seconds 60 --max-output-bytes 65536
```

La commande retourne l'ID et un **nom de fichier**, pas la clé. Un opérateur
autorisé copie uniquement ce fichier précis vers la source credential root 0600
du tableau. Ne pas afficher son contenu, le passer en argument, le stocker dans
une variable d'environnement ou donner accès au dossier `secrets/`. Le mode fichier
direct alternatif exige une copie distincte appartenant au worker en 0600 dans sa
racine, sans élargir les permissions du fichier d'origine.

Depuis le code accessible, exécuter l'initialisation sous le compte worker :

```bash
sudo -u pepeuch-b53-worker /usr/bin/python3 -E -s -B -m pepeuch_worker init \
  --worker-dir /var/lib/pepeuch-worker-b53-test/instance \
  --configuration-file /opt/pepeuch-worker-b53-test/worker-config.json
```

`init` refuse une racine existante ; il ne la répare pas. Relever les propriétaires
et modes de la racine/JSON, puis `inspect` avec le même UID. Aucun accès backend
n'est nécessaire au processus worker. Une copie du credential par un opérateur
n'est pas un contrat d'appairage LAN ; l'appairage/TLS reste à concevoir.

## 3. Gabarit et activation contrôlée

Rendre `deploy/worker-linux/pepeuch-worker-b53.service.in` dans un **fichier neuf de
revue** ; remplacer les six paramètres `@WORKER_ROOT@`, `@CODE_ROOT@`,
`@BACKEND_ROOT@`, `@CREDENTIAL_SOURCE@`, `@WORKER_UID@`, `@WORKER_GID@` par les valeurs
approuvées. UID/GID numériques, non nuls et distincts du backend. Refuser tout
paramètre restant, chemin relatif, composant `..`, espace ou caractère de contrôle.
Le `%d/worker.token` de systemd est un chemin, jamais un argument secret.

Analyser le fichier rendu avant de le copier vers `/etc/systemd/system/` :

```bash
systemd-analyze verify --man=no --generators=no /chemin/de/revue/pepeuch-worker-b53-test.service
systemd-analyze security --offline=yes /chemin/de/revue/pepeuch-worker-b53-test.service
```

Un score favorable n'est pas une preuve. Le profil propose FS hôte en lecture seule,
backend inaccessible, seul état worker inscriptible et tmp privé, aucun privilège,
capacité ou périphérique GPU, pas d'AF_UNIX/socket Docker, et limites cgroup.
CPUQuota=50% signifie au plus la moitié du temps d'un cœur, pas la moitié de tous
les cœurs ; MemoryMax=128M, SwapMax=0, TasksMax=8 (threads inclus). RuntimeMax=55s,
TimeoutStop=5s, arrêt du groupe complet, sans redémarrage automatique.
Le calcul coopératif est limité à 30s ; les échanges HTTP ont leurs propres délais.
Une limite forcée peut interrompre une publication ; le journal permet une reprise
manuelle et le serveur refuse toute tentative périmée.

`PrivateNetwork=no` conserve le loopback du backend hôte. Les filtres n'autorisent
que `127.0.0.1`, mais **ne restreignent pas ses ports**. La restriction au port API
dans `LocalClient` est applicative, pas une règle réseau OS complète. Cette lacune
et l'efficacité de l'eBPF sont des conditions bloquantes pour le mode strict.

Une seconde proposition, `deploy/worker-linux/worker-egress.nft.in`, ferme les
sorties de **tout le compte worker dédié** à TCP `127.0.0.1:<port-backend>`, puis
rejette le reste, IPv6 compris. Elle utilise une table neuve nommée, sans purge ni
remplacement d'autres tables ; le chargement échoue si ce nom existe déjà. Les
autres règles hôte peuvent encore refuser le backend. L'UID doit être exclusif,
non root et différent de tout service existant. Contrat étudié contre
[nft(8) Debian](https://manpages.debian.org/trixie/nftables/nft.8.en.html) ; ce gabarit
**n'a pas été chargé ni validé par le noyau**. Il ne fait pas partie d'une action
d'installation autorisée par cette mission.

Après **autorisation supplémentaire explicite pour le pare-feu de cette machine
jetable**, un opérateur pourra rendre les deux paramètres numériques, examiner
les règles existantes, puis faire `nft --check --file <fichier-rendu>` avant tout
chargement ciblé avec `nft --file <fichier-rendu>`. Même le contrôle noyau exige
des privilèges : il n'a pas été tenté ici. Ne pas employer de flush global ou de
service persistant nftables. Vérifier les compteurs de cette seule table pendant
les essais backend/autre port/pair contrôlé. L'exclusivité UID et les sockets
hérités restent dans la revue OS ; un fichier nftables seul n'est pas une preuve.

Après autorisation d'installation de cette unité seulement, la copier, puis :

```bash
sudo systemctl daemon-reload
sudo systemctl start pepeuch-worker-b53-test.service
sudo systemctl status --no-pager pepeuch-worker-b53-test.service
```

**Résultat attendu actuellement : refus `os_isolation_not_verified`**, sans claim
API. Aucun `enable`, timer ou restart automatique. Ce refus est un contrôle sûr,
pas un échec à contourner. Ne pas retirer la vérification du code ni inventer des
preuves. Un futur lot devra implémenter le vérificateur de confiance après les
essais OS ci-dessous.

## 4. Tests négatifs OS reproductibles — tous NOT VERIFIED

Préparer un backend de test **synthétique**, un fichier hôte canari en lecture
seule et une sortie de travail autorisée. L'opérateur vérifie que les canaris
existent hors sandbox et en relève propriétaire/mode/empreinte avant essai. Ne pas
utiliser de vrais secrets. Pour les essais, une unité de sonde dédiée reprend
**exactement les mêmes directives** que le gabarit, avec un `ExecStart` fixe vers
un programme de test relu, non vers un prompt/shell/outillage exposé au worker.
Une commande `sudo -u worker ...` seule ne teste pas les restrictions de l'unité.

| Essai à exécuter dans l'unité de sonde | Critère positif indispensable |
|---|---|
| Ouvrir en lecture le canari `secrets/admin.token`, puis `app/index.sqlite3` du faux backend | `EACCES`/`EPERM`, sans lire ni imprimer le contenu ; vérifier l'existence côté opérateur |
| Ouvrir un objet/version d'un autre workspace synthétique | Refus OS ; séparément, refus HTTP 403/404 avec une vraie identité worker |
| Ouvrir en écriture un canari hôte existant sous `/opt/` | `EROFS`/`EACCES`/`EPERM`, empreinte conservée ; ne pas écrire si l'ouverture réussit, signaler l'échec |
| Écrire dans la racine worker et le tmp privé | Réussite sur les seuls canaris prévus ; le tmp ne doit pas correspondre au tmp hôte |
| Lire `/proc/self/status`, groupes, mounts et `/proc/self/cgroup` | UID/GID non root attendus, groupes revus, NoNewPrivs=1, capabilities nulles, montages/protections observés |
| Ouvrir `/run/docker.sock`, `/var/run/docker.sock`, GPU `/dev/dri`, `/dev/nvidia*` | Refus/absence dans le namespace, comparaison à l'hôte ; aucune connexion Docker ni ouverture d'un GPU hôte |
| Connexion au backend local et à un second port loopback contrôlé | Backend accessible ; second port doit être bloqué pour une politique OS « backend uniquement » — le gabarit IP seul ne le garantit pas |
| Connexion à un pair LAN synthétique explicitement autorisé, sans envoyer de données | Refus du filtre corrélé à sa présence effective ; aucun essai vers Internet/API fournisseur |
| Vérifier `cpu.max`, `memory.max`, `memory.swap.max`, `pids.max` dans le cgroup exact de l'unité | Valeurs conformes ; l'existence des contrôleurs ou `systemctl show` seul ne prouve pas la restriction |
| Charge CPU bornée et inoffensive dans la sonde jetable | Mesure temps/usage cgroup cohérente avec le quota ; pas un benchmark de modèle |
| Essai mémoire au-delà de 128M et essai PID/threads au-delà de 8, bornés par un superviseur externe | Refus/OOM/pids.events du seul cgroup de test ; ne jamais lancer sans limites préalablement observées |
| Enfant de test fixe maintenant une attente bornée ; stop de l'unité | Parent et enfant disparus du cgroup après délai ; aucun PID extérieur affecté |
| Dépassement de RuntimeMax, puis SIGTERM et arrêt forcé séparés | Fin du groupe et de ses enfants, état serveur expiré/interrompu, résultat durable antérieur préservé |

Pour ouvrir un canari, utiliser `os.open(..., O_RDONLY|O_NOFOLLOW|O_NONBLOCK)` puis
fermer immédiatement si cela réussit (échec de l'isolation), sans imprimer d'octet.
Pour le canari hôte, utiliser `O_WRONLY` sans `O_CREAT`, `O_TRUNC` ni écriture.
`ENOENT` sur un faux chemin et `ECONNREFUSED`/timeout vers un service absent ne
prouvent pas une interdiction. Consigner résultat, errno, unit/cgroup, version,
canari et date ; ne pas collecter un dump de credentials, d'environnement ou de
données. Un réseau OS incomplet laisse le profil **non vérifié**.

Les sondes de charge et de terminaison exigent une seconde revue du programme de
test et une machine jetable. Ne pas utiliser de fork bomb, stress global, groupe
de processus arbitraire ou `kill` sans identité/cgroup vérifiés. Aucune commande
de ce tableau ne s'exécute dans les suites Python ordinaires du dépôt.

## 5. Parcours CPU fonctionnel, séparé de la preuve OS

Pour un essai applicatif explicitement consenti, `run --application-test` peut
consommer un credential worker privé dans sa racine ou via `--credential-file`.
La sortie et la provenance restent `NOT VERIFIED`, même sous une unité candidate.
Sans cette option, le refus strict précédent reste attendu. Ne pas ajouter cette
option au gabarit livré comme si elle validait l'isolation.

Créer un brouillon CPU par API en tant qu'opérateur backend, sans mettre la clé
admin dans un argument ou une variable secrète. Exemple à adapter dans ce seul
backend synthétique, **pas exécuté pendant la mission** :

```python
import http.client, json
from pathlib import Path
from uuid import uuid4

key = Path('/var/lib/pepeuch-b53-test-backend/secrets/admin.token').read_text().strip()
client = http.client.HTTPConnection('127.0.0.1', 8765, timeout=5)
headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
client.request('GET', '/api/v1/workspaces', headers=headers)
reply = client.getresponse()
assert reply.status == 200
workspace = json.loads(reply.read())['workspaces'][0]['id']
payload = {'operation_id': str(uuid4()), 'title': 'Empreinte CPU synthétique',
           'objective': 'Texte UTF-8 autorisé é', 'workspace_id': workspace, 'authorized_files': []}
client.request('POST', '/api/v1/cpu-missions', json.dumps(payload).encode(), headers)
reply = client.getresponse()
assert reply.status == 201
print(json.loads(reply.read())['id'])  # seulement l'identifiant public du brouillon
client.close()
```

Approuver ensuite ce brouillon dans la WebUI ou par la route `/missions/<id>/approve`
avec une nouvelle opération UUID. Lancer manuellement une seule tâche CPU ; comparer
SHA256 du texte UTF-8 à `input_sha256` dans `resultat.md`, puis l'empreinte du fichier
téléchargé à sa version serveur. Ce calcul n'est pas une inférence IA. Tester
`--recover` après perte de réponse, annulation, expiration, révocation et rotation
contrôlées ; vérifier le refus de l'ancienne génération, sans recréer de résultat.
Une nouvelle tentative de calcul exige une action administrative explicite.

Suites ordinaires, sans modèle ni collecte réelle :

```bash
python3 -m unittest discover -s tests/control_plane -p 'test_*.py' -v
python3 -m unittest discover -s database/poc -p 'test_*.py' -v
python3 -m unittest discover -s tests/worker -p 'test_*.py' -v
git diff --check
```

## 6. Arrêt, révocation et retrait ciblé

Arrêter **uniquement** `pepeuch-worker-b53-test.service`. Vérifier que son cgroup
est vide. Révoquer son ID via l'API administrative B5.2 ; les résultats antérieurs
restent disponibles. Pour une rotation : worker et backend arrêtés, commande
`worker-rotate`, livraison du nouveau fichier précis, ancienne tentative clôturée
et journal ancien conservé privé. La restauration backend conserve les workers
révoqués ; ne pas copier une clé ancienne pour les réactiver implicitement.

Après accord de retrait, retirer uniquement le fichier d'unité rendu et les
éventuels overrides de test **comparés et identifiés**, puis `daemon-reload`.
Si la table nftables proposée a été autorisée et réellement créée pour cet essai,
arrêter le worker d'abord, comparer `nft list table inet pepeuch_worker_b53_test`
au relevé d'installation et faire approuver son retrait ciblé. Ne retirer aucune
table préexistante ou non comparée et ne jamais purger le ruleset.
Conserver données, résultats, sauvegardes et journal tant que leur archivage n'est
pas décidé. Vérifier l'absence de processus avant de retirer un compte créé pour
cet essai ; ne pas retirer un compte préexistant. Aucun nettoyage global, suppression
de volume, prune Docker, modification d'hyperviseur ou règle réseau globale.

Avant une vraie inférence : compléter les preuves et le vérificateur strict,
fermer le réseau OS au backend, définir l'API des entrées, les politiques de moteur
et de téléchargement, puis valider des budgets adaptés. Windows/macOS nécessitent
des profils distincts ; AnythingLLM/Open WebUI demeurent facultatifs et ne remplacent
pas ces frontières de sécurité.

## 7. Plan opérateur B5.3.1 : confirmations et critères de sortie

Ce plan prépare un **pilote négatif**, pas une activation en production. Le mode
de test applicatif B5.3 reste disponible et conserve son étiquette non isolée.

| Étape | Inventaire/changement envisagé | Confirmation nécessaire avant action |
|---|---|---|
| A — revue | Machine jetable distincte, commit relu, versions noyau/systemd/cgroup, unités/comptes/groupes/règles actuels, sauvegarde des seuls états concernés | Accord sur la machine et le périmètre ; aucune action sur la VM historique |
| B — chemins/comptes | Compte worker exclusif non root, code immuable root, état privé, faux backend/canaris sous une racine neuve | Liste exacte des chemins et UID/GID ; aucun compte ou dossier préexistant réutilisé sans comparaison |
| C — fixtures | `prepare` crée uniquement des fichiers synthétiques ; canari hôte 0666 non sensible, marqueur root 0444 | Accord explicite sur ces permissions locales de test ; jamais un vrai secret ou index copié |
| D — unité/FD | Profil candidat, `ProcSubset=all` pour lire le boot ID, drop-in `OpenFile` vers un contrôleur temporaire | Revue du fichier rendu et des FD ; syntaxe seule insuffisante, pas d'élargissement AF_UNIX général |
| E — réseau | Table neuve nftables dédiée au seul UID, pairs privés contrôlés, ports et compteurs relevés | Autorisation spécifique pare-feu/pairs ; aucune purge, remplacement ou activation permanente |
| F — sondes | Cas fixes séparés, contrôle des canaris hors namespace ; lifecycle sous superviseur externe | Accord sur les seuls cas autorisés ; plafonds cgroup observés avant enfant/attente, aucun stress global |
| G — arrêt/retrait | Stop de la seule unité, cgroup vide, révocation du seul worker, conservation des résultats ; comparaison des artefacts avant retrait | Accord séparé de retrait ciblé ; préserver règles/comptes/fichiers préexistants |

Relever au préalable propriétaires/modes/ACL des racines, UID/GID effectifs et
supplémentaires, autres processus du compte, code/profil/règles et leurs SHA.
Copier aussi le package `pilot/` dans la copie de code de test relue pour utiliser
le banc ; il ne devient pas une dépendance du worker normal. Les exemples de
politique et scope sont des sentinelles publiques, invalides/périmées à remplacer.
Les ports/pairs doivent appartenir au pilote ; aucun test Internet ou fournisseur.

Le diagnostic en lecture seule peut être exécuté sans root ni service :

```bash
python3 -m pepeuch_worker.verifier \
  --configuration-file /chemin/revu/worker.json \
  --policy-file /chemin/revu/isolation-policy.json
```

Code de sortie 2 et `NOT VERIFIED` sont attendus. Une politique est une demande,
pas une preuve. Les propriétés inconnues ou incompatibles restent bloquantes.
Ne pas remplacer les contrôles par un champ `verified: true` ou un fichier approuvé.

Pour le futur test de canal, `pilot.worker_isolation.controller` est un outil root
temporaire, non démarré ici : un répertoire neuf sous `/run`, un socket root privé,
une connexion maximum, attente 20 s puis réponse de refus. Le drop-in FD n'est pas
installé. Aucun composant livré ne délivre un permis ; ne pas tenter de rendre le
profil « opérationnel » en retirant les guards. L'UID root du contrôleur et le
compte exclusif constituent des décisions de confiance à examiner séparément.

Pour les sondes, suivre le [guide du banc](../../pilot/worker_isolation/README.md).
Le faux backend est `<fixture_root>/backend`, le scope reste hors de ce sous-arbre
masqué. Ne pas considérer ces seuls refus comme la preuve que le backend final est
protégé : comparer chemins, propriétaire et montages réels. Docker/GPU sont inspectés
par métadonnées uniquement ; aucune ouverture de périphérique ni connexion Docker.
Éviter toute conclusion positive fondée seulement sur un fichier/règle présent,
un errno ambigu ou une sortie worker. Les résultats API déjà publiés restent
immutables et la restauration B5.2 révoque les anciennes identités.

Critères de sortie du pilote : preuves indépendantes versionnées, corrélées au
profil/code/règles et à l'exécution courante ; tous les tests négatifs autorisés
concluants, ressources/arrêt vérifiés, contre-épreuves de rejeu réussies, état initial
comparé après arrêt. Distinguer qualification du profil et preuves fraîches au
lancement : un arrêt/reboot/changement invalide les anciens relevés. Avant toute
émission positive, qualifier le producteur indépendant et les races entre contrôle
et utilisation ; le backend ne reçoit pas encore d'attestation OS serveur.
