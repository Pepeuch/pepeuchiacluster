# B5.0 — étude Open WebUI, AnythingLLM et worker indépendant

Sources officielles consultées le 27 octobre 2026. Étude documentaire uniquement :
aucune installation, intégration, copie de code ou création de fork. Les liens
`main`/`master` et la documentation en ligne évoluent ; choisir puis archiver une
version, sa licence, ses dépendances et son artefact exact avant un futur pilote.

## Constats vérifiés et conséquences

**Open WebUI** : depuis 0.6.6, la licence ajoute une restriction de modification
de la marque. Le texte actuel prévoit une exception pour au plus 50 personnes
ayant accès à l'application sur une fenêtre glissante de 30 jours, ou une
autorisation écrite, ou une licence entreprise spécifique. Les notices restent
requises. Le code antérieur garde ses conditions historiques. Ce n'est donc pas
une permission générale de redistribuer un fork récent rebrandé.
Sources : [LICENSE](https://github.com/open-webui/open-webui/blob/main/LICENSE),
[LICENSE_HISTORY](https://github.com/open-webui/open-webui/blob/main/LICENSE_HISTORY),
[explication officielle, versions 0.6.5/0.6.6](https://docs.openwebui.com/license/).

La licence personnalisée n'apparaît pas dans la
[liste des licences approuvées OSI](https://opensource.org/licenses).
Conclusion de conception : elle ne répond pas au critère d'une dépendance
obligatoire intégralement libre du projet. Une utilisation séparée avec sa marque
peut rester une option de l'utilisateur. Un fork de 0.6.5 évite les nouvelles
conditions pour ce code ancien, mais transfère la maintenance et les correctifs
de sécurité ; reprendre du code ultérieur exige une revue de licence.

**AnythingLLM** : le code du dépôt principal est MIT, avec conservation de la
notice et de la licence : [LICENSE du dépôt](https://github.com/Mintplex-Labs/anything-llm/blob/master/LICENSE).
**Cela ne suffit pas pour qualifier les binaires Desktop de MIT.** Leurs
[conditions spécifiques du 14 juillet 2025](https://docs.anythingllm.com/installation-desktop/terms)
accordent un usage personnel/interne non transférable et limitent notamment
modification, redistribution et intégration hors interfaces publiées. L'articulation
exacte avec le code MIT et le périmètre du binaire doivent être clarifiés avant
redistribution. Conserver Desktop comme application séparée choisie par l'utilisateur ;
ne pas le reconditionner comme composant libre du cluster sur cette seule base.

La [politique Desktop](https://docs.anythingllm.com/installation-desktop/privacy)
décrit une télémétrie désactivable. Sa disponibilité hors ligne ne dispense pas
d'examiner les connexions des modèles, outils et services externes choisis.
Proposition Pepeuch : aucun envoi de documents à un service distant sans politique
et consentement explicites, y compris depuis un client tiers.

La [présentation Desktop officielle](https://docs.anythingllm.com/installation-desktop/overview)
décrit une application Windows/macOS/Linux individuelle, avec moteur local,
RAG et agents. Elle distingue les fonctions serveur multi-utilisateurs.
La découverte réseau Desktop est désactivée par défaut : l'activer expose l'API
sur toutes les interfaces, sans ajouter d'interface web ni d'authentification
utilisateur en amont. La documentation déconseille l'exposition publique.
**Ni cette option, ni un port API ouvert, ne constituent l'appairage sécurisé
Pepeuch ou un worker autorisé.** Aucun test d'intégration n'a été réalisé ici.

## Comparaison des méthodes d'intégration

| Option | Intérêt | Coût/risques | Proposition |
| --- | --- | --- | --- |
| API avec application tierce séparée | Chat/RAG disponibles sans dépendre de son UI interne | Authentification, versions, périmètre des données et traduction d'identités à tester | Premier choix pour une option tierce ; backend Pepeuch toujours autonome |
| Extensions/plugins | Raccourcis pour confier une mission et afficher son état | Code tiers dans un processus privilégié ; API changeante ; ne donne aucune permission cluster implicite | Adaptateur mince facultatif après contrat API ; aucune exécution libre d'outils |
| Fork Open WebUI récent | Contrôle de présentation | Restrictions de marque + maintenance d'une grosse application | Écarter comme socle obligatoire libre |
| Fork Open WebUI ancien | Conditions historiques permissives | Dette de sécurité et maintenance lourde ; pas de reprise automatique du code récent | Non recommandé |
| Fork du code MIT AnythingLLM | Libertés du code couvert par MIT | Audit du périmètre, notices, dépendances et moteur ; ne résout pas les conditions Desktop distribué | Possible étude ultérieure, pas de fork B5.0 |
| UI Pepeuch minimale | Contrôle des contrats, droits, nœuds et fichiers | Développer peu d'écrans au départ ; coût de chat/RAG complet évité | Socle recommandé, interfaces tierces optionnelles |

Open WebUI documente des API authentifiées et indique leur caractère évolutif :
[API officielles](https://docs.openwebui.com/reference/api-endpoints/).
AnythingLLM documente une API développeur et la gestion des clés, avec description
sur l'instance : [API et clés](https://docs.anythingllm.com/features/api).
Ces API sont des points d'intégration candidats, pas un protocole de worker,
une garantie d'isolation ou une validation d'inférence Pepeuch.

Pour un futur POC : épingler les versions et tester les capacités réellement
disponibles dans **l'édition choisie**, l'identité transmise, les droits minimaux,
le streaming, l'annulation et les erreurs. Un pont de chat compatible ne doit pas
transformer une complétion ou un appel d'outil en mission sans accord utilisateur.
Les clés tierces restent côté backend/pont local, jamais dans les fixtures.

## AnythingLLM comme moteur local ou worker

| Variante | À réutiliser éventuellement | Contrats manquants pour Pepeuch | Position |
| --- | --- | --- | --- |
| Desktop seul, API LAN activée | Expérience conversationnelle locale | Identité de nœud, appairage mutuel, autorisation par tâche, réservations, bail, révocation et persistance cluster non démontrés | Ne pas assimiler à un worker sécurisé |
| Compagnon Pepeuch + Desktop séparé | UI utilisateur et éventuellement moteur via une interface publiée locale | Pont explicitement consenti, versions/conditions, limites de ressources, santé et isolation à vérifier | Facultatif ; API Desktop reste sur loopback |
| Worker indépendant + runtime local remplaçable | Protocole cluster stable et supervision du runtime choisi | Worker à développer ; validation par OS/runtime et sécurité à prouver | Chemin recommandé |
| Instance serveur AnythingLLM séparée | Chat/RAG partagé potentiel | Traduction des utilisateurs/permissions/workspaces ; autonomie du backend Pepeuch | Client/service optionnel, pas la source de vérité |

Cette comparaison des contrats manquants est une analyse Pepeuch, pas une
affirmation que ces projets auraient promis un worker distribué. Le backend doit
continuer de fonctionner sans eux. Le companion contrôle le consentement local ;
le worker applique les baux et limites ; le runtime assure le calcul. Une API de
chat peut être l'une des capacités d'un nœud sans lui donner accès aux fichiers,
aux bases, aux secrets des autres fournisseurs ou au shell de l'hôte.

## Décisions et risques à examiner

Recommandation : **UI minimale libre + backend indépendant + worker indépendant**,
avec intégrations par API séparées. Le choix précis de runtime reste ouvert.
Les conditions Desktop actuelles sont un point bloquant pour sa redistribution
comme composant Pepeuch, pas pour poursuivre cette étude sans installation.
La revue d'un artefact/édition exacts reste nécessaire avant engagement.

Avant B5.1 : approuver les contrats de mission et d'appairage, la licence des
dépendances embarquées, la politique de télémétrie et la matrice de tests OS.
Les fonctions de chat avancé, extensions exécutables, RAG, plugins communautaires,
accès distant et forks ne sont pas requis avant le premier agent. Aucun « local »
ne garantit à lui seul la confidentialité, l'autorisation ou une isolation d'hôte.
