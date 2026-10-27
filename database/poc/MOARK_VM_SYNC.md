# Synchroniser B3.3 sur la VM sans perdre les fichiers locaux

Procédure à exécuter sur Debian 13 dans `/opt/pepeuch-ai/repo`, après le push
sur `origin/feat/db-poc-models-dev`. Aucun import en base ni nouvel appel MoArk.
Remplacer la valeur `B33_COMMIT` par le **SHA complet fourni après publication**.
Exécuter ce bloc dans un sous-shell Bash : un arrêt ne ferme pas la session SSH.

Les cinq fichiers initialement non suivis sont nommés explicitement ci-dessous.
Les documents suivis (`TODO.md`, `DISCOVERY_CACHE_B2.md`) et les autres fichiers
ne sont pas inclus dans le stash ciblé. Les nouveaux documents de synchronisation
seront apportés par le pull. Aucun ancien stash n'est supprimé ou réappliqué.

```bash
(
set -euo pipefail
cd /opt/pepeuch-ai/repo
B33_COMMIT='REMPLACER_PAR_LE_SHA_COMPLET_PUBLIE'
branch='feat/db-poc-models-dev'
test "$(git branch --show-current)" = "$branch"
test "$(git remote get-url origin)" = 'https://github.com/Pepeuch/pepeuchiacluster.git'

# 1. Récupérer les références ; ne rien modifier dans l'arbre de travail.
git fetch origin
test "$(git rev-parse "${B33_COMMIT}^{commit}")" = "$B33_COMMIT"
test "$(git rev-parse "refs/remotes/origin/$branch")" = "$B33_COMMIT"
git merge-base --is-ancestor HEAD "$B33_COMMIT"

# Arrêter si des fichiers suivis ou l'index sont modifiés, même hors B3.3.
# Ils restent intacts ; les examiner séparément avant de reprendre.
git diff --quiet
git diff --cached --quiet
test -z "$(git ls-files --unmerged)"
git status --short --branch
git stash list

# 2. Comparer tous les candidats AVANT le premier stash.
paths=(
  database/poc/MOARK_B3.md
  database/poc/fixtures/moark_models.synthetic.json
  database/poc/moark_adapter.py
  database/poc/probe_moark.py
  database/poc/test_moark_adapter.py
)
to_stash=()
for path in "${paths[@]}"; do
  # Le fichier doit exister comme fichier normal dans le commit publié.
  entry=$(git ls-tree "$B33_COMMIT" -- "$path")
  test "${entry%% *}" = '100644'
  if git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    # Cas d'une synchronisation déjà faite : les fichiers suivis sont propres.
    continue
  fi
  if test -e "$path" || test -L "$path"; then
    test -f "$path" && test ! -L "$path"
    # Des octets identiques sont exigés, sans filtre Git ni conversion implicite.
    if test "$(git hash-object --no-filters -- "$path")" != \
            "$(git rev-parse "$B33_COMMIT:$path")"; then
      printf 'DIFFERENT : %s ; arrêt sans stash ni pull.\n' "$path" >&2
      exit 1
    fi
    to_stash+=("$path")
  fi
done

# 3. Sauvegarder uniquement les fichiers non suivis comparés et identiques.
if ((${#to_stash[@]})); then
  git stash push --include-untracked \
    -m "VM B3.3 identical local files before $B33_COMMIT" \
    -- "${to_stash[@]}"
  printf 'Stash conservé : %s\n' "$(git rev-parse refs/stash)"
fi

# 4. Épingler le pull au SHA comparé, même si la branche distante bouge ensuite.
# Aucun reset, clean, checkout forcé ou push n'est utilisé.
git pull --ff-only origin "$B33_COMMIT"

# 5–6. Tests hors ligne, branche et commit attendus.
python3 -m unittest discover -s database/poc -p 'test_*.py' -q
git diff --check
test "$(git branch --show-current)" = "$branch"
test "$(git rev-parse HEAD)" = "$B33_COMMIT"
git status --short --branch
git log -1 --format='%H %s'
git stash list
)
```

Résultat attendu pour ce commit : **91 tests réussis**, branche
`feat/db-poc-models-dev`, HEAD égal au SHA publié. Les fichiers non suivis sans
rapport avec B3.3 et tous les anciens stashes restent présents. Git peut refuser
le pull si un autre fichier non suivi entre en collision : conserver ce refus,
comparer ce fichier séparément et ne pas lancer de nettoyage global.

Si le contrôle signale un fichier différent, la procédure s'arrête avant toute
sauvegarde ou écriture dans l'arbre. C'est notamment possible pour
`MOARK_B3.md` : sa version initiale disait que les imports restaient à exécuter,
alors que le rapport publié intègre leur validation sur la VM.

Pour examiner un tel écart, extraire **la seule version distante** dans un
nouveau répertoire temporaire, sans remplacer le fichier local :

```bash
# Dans le dépôt, avec le même SHA B33_COMMIT que ci-dessus.
review_dir=$(mktemp -d /tmp/moark-b33-review.XXXXXXXX)
git show "$B33_COMMIT:database/poc/MOARK_B3.md" > "$review_dir/MOARK_B3.published.md"
git diff --no-index -- database/poc/MOARK_B3.md "$review_dir/MOARK_B3.published.md"
# Un code de retour 1 signifie que les fichiers diffèrent.
```

Conserver une copie du fichier local dans un répertoire de sauvegarde distinct
avant toute résolution manuelle, puis vérifier cette copie avec `cmp`. Examiner
le diff et décider explicitement de la résolution. Le bloc principal ne
remplace jamais automatiquement un fichier divergent ; ne le reprendre que
lorsque les candidats présents sont identiques aux versions publiées. Les
documents suivis modifiés nécessitent le même examen séparé. Après le pull,
le stash ciblé reste une sauvegarde : ne pas l'appliquer automatiquement aux
fichiers désormais suivis. Relever son OID pour le retrouver indépendamment
de sa position dans la liste des stashes.
