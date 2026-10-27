# B4.1 — primitives communes sans changement de payload B2/B3

Lot validé après B4.0 : **122 tests**, dont 91 historiques, 17 de référence et
14 nouveaux cas sur les primitives et leurs intégrations. Les sept snapshots,
leurs clés et empreintes restent strictement identiques aux valeurs capturées
sur B3.3. Le fichier `reference.b33.json` n'a pas été modifié.

## Mutualisations effectuées

`metadata_primitives.py` ne contient aucune règle de fournisseur ou d'identité :

- `object_value` et `nonempty_string` reprennent exactement les validations B1,
  sans trim, coercition ou valeur par défaut. Les noms privés `_object`/`_string`
  restent disponibles dans `source_adapters` par import.
- `optional_nonnegative_int` mutualise les compteurs optionnels ModelScope/CSGHub :
  null reste null, zéro reste un entier, booléens et nombres négatifs sont refusés.
  Les wrappers existants conservent leurs signatures et libellés de champs.
- `copy_metadata` copie les structures JSON et refuse valeurs non finies, clés
  non textuelles, cycles et clés de credentials. Le callback SDK n'est autorisé
  que lorsqu'il est explicitement fourni ; ModelScope garde sa conversion
  Enum/date/datetime existante. Le résultat de la conversion est aussi contrôlé.
- `strict_json_loads` refuse clés répétées, syntaxe invalide, UTF-8 invalide,
  NaN/Infinity et flottants hors plage. Il ne choisit pas arbitrairement la
  dernière valeur d'une clé répétée. Il ne décide pas du schéma racine d'une API.
- `error_summary` expose uniquement un label interne, la classe d'erreur ou un
  code HTTP numérique ; il ne formate jamais le contenu de l'exception.

Les trois normaliseurs B3 réutilisent la même copie au lieu de leurs variantes
locales. Les règles d'accès, visibilité, licence, révision et sélection restent
dans leurs modules. Les erreurs HTTP NIM 404 gardent leur traitement particulier.

## Données possédées et protection des snapshots

`SourceRecord.__post_init__` copie attributes, relations et métadonnées brutes.
Cela couvre les sept sources, y compris les TOML locaux via le collecteur B2,
et protège le contrat même si un nouveau collecteur construit directement
`SourceRecord`. Un objet d'entrée muté ensuite ne modifie plus le record.

`record_payload` renvoie une copie et `make_snapshot` copie le scope. Modifier
un record, ses relations ou la sélection après la création d'un snapshot ne
change donc pas ses données ni ses empreintes. Les dicts restent des dicts : un
appelant peut encore modifier volontairement un snapshot ; l'intégrité se
contrôle toujours par `validate_snapshot`. Il ne s'agit pas d'un nouveau format.

Le JSON de référence conserve les observations **historiques** de partage
mémoire B3.3. Les deux tests B4.0 concernés ont été adaptés dans ce lot pour
vérifier l'isolation nouvelle, tout en comparant les mêmes payloads littéraux.
Les 15 autres tests de référence et les 91 tests historiques restent inchangés.

## Périmètre du durcissement

Les sondes de fixture et les lecteurs JSON HTTP B1/B3 utilisent le parseur
strict. Les CLI de comparaison et de génération d'imports le réutilisent avant
toute sortie. Les erreurs des sondes et outils B2 sont résumées sans corps,
URL, chemin utilisateur ou valeurs de champs. Les modes, arguments et résultats
stdout valides des CLI sont conservés ; les diagnostics stderr sont volontairement
moins détaillés. Aucun retry ni transport commun ajouté à ce stade.

Le rejet récursif reconnaît les variantes de casse/séparateurs de clés comme
`api_key`, `accessToken`, headers d'autorisation/cookies et clés privées. Les
compteurs `max_tokens`, `token_count` et les informations de tokenizer restent
valides. C'est une barrière par **nom de champ**, pas un détecteur universel de
secrets dans du texte libre : ne jamais charger ni joindre de credentials à la
collecte de métadonnées. Les fixtures de test n'utilisent que des sentinelles
synthétiques explicites.

Incompatibilité intentionnelle d'entrée : des métadonnées contenant des clés
de credentials, du JSON ambigu ou des valeurs non finies sont désormais refusées
plus tôt et plus uniformément. Aucun des snapshots de référence ni des résultats
valides déjà importés n'a changé. Les snapshots historiques conservant d'éventuels
credentials ne sont pas considérés comme des entrées sûres à réimporter.

## Décisions conservées pour les lots ultérieurs

- Ne pas unifier public/autorisé/téléchargeable ni modifier le cas ModelScope
  public + gated, les inconnues ou les formats observés.
- Ne pas changer les namespaces ni l'identité NIM pour accepter plusieurs tags.
- Ne pas ajouter synthétique/réel ou compte/domaine dans les payloads historiques :
  convention d'observation et évolution de scope à concevoir explicitement.
- La protection commune n'implique pas une lecture réseau : B4.2 préparera une
  primitive HTTP injectable et un contrat SDK, sans migration implicite ni retry.
