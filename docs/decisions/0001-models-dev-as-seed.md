# ADR-0001 — models.dev comme seed principal

Utiliser `anomalyco/models.dev` comme première source généraliste du catalogue.
Les données sont importées via un adapter vers notre schéma normalisé.
Aucun composant runtime ne doit dépendre directement du format TOML/JSON upstream.
