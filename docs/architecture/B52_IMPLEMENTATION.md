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
