# B5.3.1 — contrat de vérification Linux

## État effectif

Le diagnostic et le contrôle du canal sont implémentés, **pas une qualification
OS complète**. Le vérificateur diagnostique livré n'émet que `deny`/`NOT VERIFIED`.
Le lancement strict sans autorité indépendante continue de lever
`os_isolation_not_verified`, avant lecture du credential et attribution API.
Aucun fichier JSON, booléen, résultat de sonde ou changement de propriétaire d'un
rapport worker ne permet d'obtenir un permis. Les succès de protocole dans les
tests sont des fixtures, jamais des preuves d'isolation réelle.

Le client est préparé pour contrôler une future décision `permit` émise par une
autorité indépendante compatible. **Aucun producteur qualifié de ces permis n'est
livré ou démarré dans ce lot** : il faut d'abord exécuter les tests OS sous contrôle
opérateur et qualifier leur collecte. Le contrôleur temporaire proposé permet de
tester le chemin de refus, pas d'activer artificiellement le worker.

## Contrats versionnés

| Schéma (`pepeuch.worker/…/v1`) | Sens et confiance |
|---|---|
| `isolation-policy` | Exigences demandées : profil, empreinte de configuration, unité/invocation, cgroup, groupes, chemins et plafonds. Fermé, borné, chemins disjoints. Une politique ne prouve pas son application. |
| `linux-observations` | Lectures bornées de `/proc` et cgroup v2, contexte et données effectivement visibles. Les racines alternatives sont marquées synthétiques. Aucune auto-attestation. |
| `isolation-receipt` | Portée et fraîcheur attendues d'un futur relevé de tests indépendants. Sa validation structurelle ne l'authentifie pas. |
| `isolation-assessment` | Différences exigences/observations, garanties inconnues, erreurs explicites. Toujours `NOT VERIFIED` pour des entrées non authentifiées. |
| `verification-request` | Nonce aléatoire, configuration publique validée et contexte courant du processus. Aucun credential ni objectif utilisateur. |
| `verification-decision` | Réponse d'une autorité indépendante : nonce/contexte/configuration/profil/politique/relevé, lease de deux secondes maximum et couverture de toutes les garanties. |

Le contexte lie PID, starttime noyau (réutilisation PID), boot ID, noyau,
UID/GID réels/effectifs/sauvés/fs, groupes, capacités, namespaces user/mount/net/pid/
cgroup/time et cgroup/inode. La politique et le relevé ajoutent unité, invocation
et empreinte canonique de configuration/politique. La configuration effective est
copiée : modifier le JSON d'origine n'altère pas celle du processus déjà lancé.

Un nom `.service` déduit du cgroup est seulement un indice. Le contrôleur peut
recueillir `Id`, `MainPID`, `ControlGroup`, `InvocationID`, `KillMode` et délais par
une commande fixe `systemctl show` en lecture seule, bornée à une seconde. Les
valeurs d'un fichier d'unité ne remplacent pas ces observations et les essais.

Rejet des reçus absents, périmés/futurs/non finis, mauvaises identités/profil/
configuration/politique/invocation, redémarrage ou namespace/cgroup différents,
tests manquants, méthode auto-déclarée ou garantie inconnue. Aucun repli cgroup v1,
limite `max`, contrôleur manquant ou lecture tronquée n'est converti en réussite.

## Frontières de confiance

| Acteur | Responsabilité | Ce qu'il ne peut pas prouver seul |
|---|---|---|
| Worker | Valider la tâche typée, respecter le protocole, demander une autorisation fraîche | Son propre isolement, l'exclusivité UID ou le filtrage réseau |
| Lanceur de confiance | Code/profil relus, UID/groupes, FD autorisés, namespace initial, configuration versionnée | L'efficacité d'un fichier nftables ou d'une option systemd sans essai |
| Opérateur | Autoriser le pilote, inventaire synthétique, droits minimaux, contrôles externes, arrêt/retrait ciblés | Transformer une sortie worker en preuve en la copiant/chmodant |
| Vérificateur indépendant | Refaire les mesures, corroborer les sondes et leur contexte, refuser toute ambiguïté | Défendre contre un administrateur root compromis ; celui-ci est dans la base de confiance |
| Backend | Identité API, epoch/génération, publication durable et provenance contrôlée | Déduire l'isolation d'un résultat CPU ou d'un booléen reçu du worker |

Le backend reste inchangé et **n'accepte aucune promotion `verified` fournie par
le worker**. Les résultats CPU gardent leur provenance OS `NOT VERIFIED`, même
si un futur contrôle local de lancement aboutit. Une attestation serveur serait
un contrat supplémentaire, à concevoir et valider séparément.

## Canal hérité, sans service privilégié permanent

Proposition pour le futur pilote seulement : contrôleur root temporaire hors du
worker, socket root privé, une connexion maximum, attente de 20 s, lecture/écriture
de 2 s, durée maximale logique 55 s et au plus huit demandes. La version livrée
répond au premier diagnostic par un refus puis ferme. Elle n'installe rien.

`deploy/worker-linux/verifier-fd.conf.in` propose `OpenFile` : PID1 connecte le
socket et transmet le FD avant les restrictions du worker. Disponible depuis
systemd 253 dans la [documentation Debian systemd.service](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html).
Le worker garde `RestrictAddressFamilies=AF_INET` : il ne reçoit pas une permission
générale de créer des sockets Unix. Le FD n'est pas un secret. L'indice 3 suppose
une unité neuve sans autres sockets activés/FD hérités ; vérifier cet inventaire,
ne pas réutiliser une unité existante à l'aveugle.

Le client contrôle `SO_PEERCRED`, son namespace UID initial et les credentials
**de chaque message** avec `SO_PASSCRED`/`SCM_CREDENTIALS`. Les credentials de
connexion reflètent sa création et ne suffisent pas si un FD a été transmis à un
autre processus. Voir [unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html).
Le contrôleur distingue également PID1 créateur de la connexion du worker auteur
du message ; il refait les observations pour ce PID effectivement reçu du noyau.
Un auteur non root ne peut pas simplement fournir `issuer_uid: 0` dans du JSON.

Le framing est borné et sous deadline ; credentials manquants, tronqués, multiples
ou changeants, FD inattendus et mauvais types sont refusés. Les FD reçus par erreur
sont fermés. Nonce et contexte empêchent la réutilisation d'une réponse pour un
autre appel ; contrôleur, politique et contexte sont épinglés pendant la session.
Le runner demande un contrôle avant claim, avant calcul et avant finish/reprise.
La perte de preuve bloque la publication tout en conservant le journal durable.

## Ce qui est observé, ce qui reste à qualifier

- Observations : identités, groupes, NoNewPrivileges, cinq ensembles de capacités,
  seccomp, contexte d'exécution, mounts et limites cgroup au chemin attendu.
  Options de montage inconnues potentiellement sensibles supprimées des rapports ;
  inventaire FD sous forme de types/empreintes, sans contenus de fichiers.
- Comparaisons : tous les UID/GID non root attendus, groupes exacts, privilèges
  nuls, cgroup v2, CPU borné, mémoire/PID finis, swap nul, montage couvrant le code
  en lecture seule, correspondance unité/invocation/PID/cgroup si observée.
- **Non qualifiés** : compte exclusif, véritable identité backend, code immuable
  depuis l'hôte/autres processus, FS complet et entrées, Docker/GPU, filtrage IPv4/
  IPv6/ports, origine des sockets hérités, durée et arrêt de groupe. Ils restent
  des garanties obligatoires inconnues, pas des succès.

La documentation [cgroup v2 du noyau](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
sert à interpréter les interfaces. Lire une valeur n'est pas un essai de charge.
Le PID controller compte aussi les threads ; les restrictions héritées ne doivent
pas justifier un repli silencieux sur un fichier manquant. `cpu.max` est vérifié
au cgroup du processus, sans extrapoler depuis la seule liste des contrôleurs.

`ProcSubset=pid` masquerait le boot ID requis sous `/proc/sys`. Le gabarit proposé
utilise désormais `ProcSubset=all`, en conservant `ProtectKernelTunables=yes`, les
autres protections et la lecture seule. Ce changement est **un gabarit non activé**,
à vérifier sur Debian 13. Aucun montage ou paramètre hôte n'a été modifié ici.

## Avant un permis réel

Qualifier la chaîne d'observations externes et l'origine des tests, versionner
code/unité/règles, corréler les compteurs noyau et l'inventaire des canaris, contrôler
les FD hérités et le compte exclusif. Une copie root d'un JSON worker ne suffit
pas. Les épreuves destructives du cgroup (arrêt/expiration) nécessitent un
superviseur externe et des identités recontrôlées ; distinguer qualification du
profil et contrôle frais de chaque lancement. Toute modification ou redémarrage
invalide les anciens relevés. Le producteur qualifié de permis reste bloqué tant
que ce pilote n'apporte pas ces preuves. Aucun bouton/flag ne doit sauter cette étape.
