# B5.2 — isolation OS : étude séparée, aucun provisionnement

État réel : worker déterministe, même compte OS que le backend, pas d'outils
arbitraires. Les rôles API et les credentials sont distincts ; **ils ne constituent
pas une séparation OS**. Le registre expose cette absence d'isolation appliquée.

## Comparaison des options Linux

| Option | Frontière utile | Limites et conditions | Proposition |
| --- | --- | --- | --- |
| Processus distinct, même UID | Arrêt et supervision séparés | Peut accéder aux fichiers/credentials du compte ; insuffisant face à un processus hostile | Démo actuelle uniquement |
| UID de service distinct | Droits d'accès POSIX séparés, credential worker propre | Il faut déléguer le credential sans donner accès à la racine backend ; privilèges/capabilities et permissions à vérifier | Premier pilote d'isolation à autoriser séparément |
| UID + restrictions systemd + cgroup v2 | Répertoires, périphériques et ressources mieux limités | Options disponibles selon version/noyau/délégation ; ne remplace pas une politique réseau ou un audit des outils | Candidat Linux à tester avant un outil réel |
| Conteneur rootless borné | Namespace utilisateur et système de fichiers dédié | Partage du noyau, délégation cgroups variable, surface runtime ; aucun socket hôte ou montage libre | Option ultérieure, sans installation B5.2 |

Sources officielles consultées :
[environnement systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html),
[contrôleurs cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html),
[fonctionnement rootless Docker](https://docs.docker.com/engine/security/rootless/).
Ces documentations décrivent des mécanismes disponibles, pas une preuve de
sécurité du futur profil Pepeuch. Ne pas appliquer les options d'une version
systemd récente sans vérifier celles de Debian 13. Aucun service/unité n'est créé.

## Contrat candidat d'isolation v1 — NON IMPLÉMENTÉ

Le profil devra lier identité worker, utilisateur OS, runtime/version, périmètre
de fichiers, outils explicitement autorisés, réseau sortant, capacités système,
périphériques, limites CPU/mémoire/PID/disque, deadline et mécanisme d'arrêt.
Chaque garantie portera `declared`, `enforced` et `verified`, avec date et preuve
du test ; une option absente ne doit pas être promue en capacité appliquée.

Le worker n'aura ni accès à `app/`, aux secrets admin, aux sauvegardes ou aux bases
POC, ni sudo, socket Docker hôte, montage arbitraire ou périphérique GPU par défaut.
Les entrées seront des copies autorisées en lecture seule et les sorties un staging
par tentative. L'exécuteur devra rester une interface typée : jamais une commande
shell issue d'un prompt. L'identité réseau ne prouve pas le profil OS de la machine.

B5.2 applique seulement : capacité `demo.report.v1`, une tentative active, limite
d'octets de sortie, contrôle des échéances/résultats et transport loopback. Ce ne
sont pas des quotas physiques CPU/RAM ni une préemption de calcul arbitraire.

## Preuves exigées avant un futur pilote

Dans une machine de test explicitement autorisée : refus de lecture d'un secret
admin et d'un autre workspace, refus d'écriture hors staging, absence de privilèges
et de périphériques, refus réseau externe, saturation CPU/RAM/PID, arrêt d'un enfant,
expiration/révocation en cours et conservation des résultats déjà validés. Prévoir
un test négatif démontrant que les restrictions sont réellement appliquées.

Windows et macOS exigent des profils et preuves distincts ; le contrat logique
peut rester commun, pas les garanties d'isolation. Ni conteneur, UID dédié,
driver, runtime IA, LAN ou agent réel n'est installé/activé dans ce lot.
