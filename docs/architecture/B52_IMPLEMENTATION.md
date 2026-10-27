# B5.2 — sécurisation et résilience

Base : `a822b4d`, merge publié de B5.1 (`a4c537c`) vérifié après fetch. `main`
actualisé par avance rapide uniquement ; branche `feat/webui-control-plane-b52`.
Arbre initial propre, 341 tests de départ réussis. Commits locaux, aucun push.

## B5.2a — HTTP : garanties locales testées

Le parseur accepte un sous-ensemble explicite HTTP/1.0–1.1 : CRLF, GET/POST,
chemin origin-form, aucun doublon d'en-tête, repli, transfert chunked, upgrade ou
Expect. Fermeture après une requête ; HEAD refusé sans corps. Les fichiers
statiques passent les mêmes contrôles de framing/hôte/origine. Erreurs constantes,
sans chemin, corps ou credential ; `no-store` et protections WebUI sur les erreurs
également. Les autorisations B5.1 restent inchangées.

Limites : ligne de requête 2048 octets, ligne d'en-tête 4096, en-têtes cumulés
16384, 32 en-têtes, corps 1 500 000, 16 connexions actives. Deadline absolue de
lecture de 5 secondes, sans remise à zéro à chaque octet. Client worker : réponse
JSON cadrée par une longueur unique, sans compression, 128 Kio maximum ; deadline
de lecture, aucun proxy ou suivi de redirection. Aucun retry implicite.

85 tests Control Plane réussis (69 B5.1 conservés + 16 nouveaux) : wire HTTP,
troncature, ambiguïtés, limites, timeout, saturation/récupération et deadlines
injectées. La première exécution a révélé `flush()` manquant lors d'une fermeture
anticipée du lecteur ; correction validée par le test de redirection existant.

Références officielles : [syntaxe et framing RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html),
[limites de http.server](https://docs.python.org/3.13/library/http.server.html).
Il ne s'agit ni d'une implémentation HTTP générale ni d'une validation production.
Pas de TLS, exposition LAN, reverse proxy, débit garanti ou préemption de logique
métier. Les délais bornent les I/O, pas une fonction métier bloquée.

## B5.2b — sauvegarde/restauration hors ligne

IMPLÉMENTÉ : `backup` et `restore`, explicitement lancés en CLI. Verrou exclusif
de backend obligatoire ; refus d'un journal SQLite/WAL restant à récupérer.
Index en lecture seule, contrôle d'intégrité/FK/schéma connu, références et SHA256
des objets vérifiés. Référence : [sauvegardes SQLite](https://www.sqlite.org/backup.html)
et [contrôles SQLite](https://www.sqlite.org/pragma.html#pragma_integrity_check).

La sauvegarde est un **dossier privé 0700**, pas une archive publiable : SQLite,
les deux fichiers de configuration connus, objets référencés et manifeste versionné.
Secrets, logs, staging et objets orphelins sont exclus, sans suppression côté source.
Les données applicatives peuvent être privées : ne jamais partager ce dossier
comme s'il était expurgé de tout contenu sensible. Les SHA256 détectent une
corruption, pas un remplacement malveillant de tout le manifeste.

La destination doit être inexistante ; création exclusive sans écrasement.
Manifeste de sauvegarde écrit en dernier. À la restauration, validation intégrale
avant création de destination, copie revérifiée, nouvelles clés et marqueur
d'installation écrit en dernier. Une interruption conserve une copie incomplète
privée et refusée ; aucune restauration/prune ou suppression automatique.
Répertoire parent et compte local de confiance supposés, pas de garantie NFS.

TESTÉ : 101 tests Control Plane cumulés (+16) ; mission → worker → publication →
sauvegarde → restauration ailleurs → redémarrage → mêmes IDs, événements, octets
et SHA256. Credentials source absents de la copie et refusés sur la restauration.
Refus de source active, destination existante, schéma modifié, chemins/liens,
index/manifestes/objets corrompus, références invalides et copies interrompues.
Pas de simulation de panne électrique ni de sauvegarde hors machine déjà déployée.

Limites bornées : index 256 Mio, manifeste 4 Mio, au plus 10 003 fichiers décrits
et 2 Gio de contenu. Les backups dépassant le format/les limites sont refusés.
Rétention sans purge. Les workers d'un registre restauré seront révoqués avant
acceptation ; un réenrôlement explicite est requis dans le lot identité.
