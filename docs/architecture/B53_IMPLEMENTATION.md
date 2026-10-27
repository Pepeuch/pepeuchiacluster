# B5.3 — worker CPU indépendant, validation OS séparée

Base publiée vérifiée : `ef5b293ae91132ff0fda0431318b649184e14348` (merge B5.2).
Branche `feat/webui-control-plane-b53`, arbre initial propre. Aucun push, merge,
installation, compte système, changement de permissions hôte ou action sur la VM.

## B5.3a — contrat

`pepeuch.worker/config/v1` distingue ID cluster opaque, UID/GID attendus, UID du
backend, endpoint loopback, capacités, outils et limites. Configuration fermée,
sans credential dans le JSON, sans variable d'environnement secrète. Le premier
exécuteur ne reçoit que le texte de l'objectif approuvé, pas des chemins de fichiers.
La capacité `cpu.text.sha256.v1` désigne un calcul déterministe CPU, pas une IA.

Chaque propriété du rapport `pepeuch.worker/security-evidence/v1` distingue
`declared`, `enforced` et `verified`, avec origine de preuve. Une déclaration,
une authentification API ou un booléen fourni dans la configuration ne suffit pas.
Un profil obligatoire incomplet doit refuser l'exécution.

Les missions, tentatives/générations, epochs de credential, révocation, reprises
manuelles et publication durable B5.2 restent les frontières du protocole.
Le worker historique et son point d'entrée restent disponibles par défaut.

TESTÉ à ce lot : six tests de contrat purs ; aucune preuve d'isolation OS simulée
ne sera présentée comme réelle. La validation système devra être faite sur une
machine distincte explicitement autorisée, pas sur la VM actuelle.
