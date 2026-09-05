#!/bin/bash
# deploy.sh — remplacer un livre de la bibliothèque Jeunesse par le canal calibre-web.
#
# ⛔ JAMAIS par USB : le sideload supprime la fiche du livre et la réimporte, ce qui
#    détruit annotations ET position de lecture, définitivement (mesuré le 04/09/2026,
#    cadratin/docs/annotations-canal-de-remplacement-2026-09-04.md).
#
# Le canal : Drive (source de vérité) → cron */2 de cigogne → ~/data → kepub-batch.
# Écrire directement dans ~/data ne servirait à rien : le rclone copy du cycle
# suivant restaure la version du Drive.
#
#   deploy.sh <epub-corrigé> <"Auteur/Titre (id)"> <id-calibre-web> [--go] [--malgre-tout]
# Sans --go, rien n'est écrit : le script montre ce qu'il ferait.
#
# ⚠ Étape 0 : le contrôle d'avant-vol. Une passe typographique déplace les ancres
#   koboSpan, et une annotation glisse alors EN SILENCE vers la phrase voisine.
#   Le serveur ne sait rien des surlignages — c'est le registre alimenté par
#   kobo_moisson.py qui le dit. Le script s'arrête si le livre est annoté et que
#   des ancres bougent ; --malgre-tout passe outre en connaissance de cause.
set -u
EPUB="$1"; RELPATH="$2"; BOOKID="$3"; GO=""; FORCE=""
for arg in "${@:4}"; do
  [ "$arg" = "--go" ] && GO="--go"
  [ "$arg" = "--malgre-tout" ] && FORCE="oui"
done
OUTILS="${OUTILS:-$HOME/src/bp/epub-typo-fr}"
REGISTRE_DISTANT="${REGISTRE_DISTANT:-kobo-annotations/registre.json}"
NAME="$(basename "$EPUB")"
REMOTE="gdrive1:Documents/Jeunesse/$RELPATH/$NAME"
MD5="$(md5sum "$EPUB" | cut -d' ' -f1)"
say () { printf '\n\033[1m%s\033[0m\n' "$*"; }
run () { if [ "$GO" = "--go" ]; then eval "$@" || echo "   ⚠ échec"; else echo "   [à blanc] $*"; fi; }

say "0. contrôle d'avant-vol — ce que ce déploiement coûte aux annotations"
UUID=$(ssh cigogne "sqlite3 \$HOME/data/metadata.db \"SELECT uuid FROM books WHERE id=$BOOKID;\"")
TMPK=$(mktemp -d)
ssh cigogne "cat \"\$HOME/data/$RELPATH/\"*.kepub" > "$TMPK/actuel.kepub" 2>/dev/null
ssh cigogne "cat \$HOME/$REGISTRE_DISTANT" > "$TMPK/registre.json" 2>/dev/null
if python3 "$OUTILS/deploy_preflight.py" --registre "$TMPK/registre.json" --uuid "$UUID" \
     --kepub-actuel "$TMPK/actuel.kepub" --epub-nouveau "$EPUB"; then
  rm -rf "$TMPK"
else
  rm -rf "$TMPK"
  if [ -z "$FORCE" ]; then
    echo
    echo "   ⛔ arrêt. Relancer avec --malgre-tout pour déployer quand même,"
    echo "      puis recoller les ancres liseuse branchée (kobo_reancre.py --go)."
    exit 3
  fi
  echo "   ⚠ --malgre-tout : on déploie en sachant que des ancres vont glisser."
fi

say "1. état avant  (md5 attendu après déploiement : $MD5)"
ssh cigogne "ls -la \"\$HOME/data/$RELPATH/\" | sed -n '2,9p'; \
  md5sum \"\$HOME/data/$RELPATH/$NAME\" | cut -c1-32; \
  sqlite3 \$HOME/data/metadata.db \"SELECT id,title,timestamp,last_modified FROM books WHERE id=$BOOKID;\"; \
  docker exec calibre-web sqlite3 /config/app.db \"SELECT group_concat(user_id) FROM kobo_synced_books WHERE book_id=$BOOKID;\""

say "2. déposer le fichier corrigé sur le Drive, sous le même nom"
run "scp -q '$EPUB' cigogne:/tmp/depot.epub"
run "ssh cigogne \"rclone copyto /tmp/depot.epub '$REMOTE' && rm -f /tmp/depot.epub\""

say "3. attendre que le cycle (*/2 min) le redescende dans ~/data"
run "ssh cigogne \"for i in \\\$(seq 1 60); do \
       if [ \\\"\\\$(md5sum \\\"\\\$HOME/data/$RELPATH/$NAME\\\" 2>/dev/null | cut -d' ' -f1)\\\" = '$MD5' ]; then \
         echo '   descendu au bout de '\\\$((i*10))'s'; exit 0; fi; sleep 10; done; \
       echo '   ⚠ toujours pas descendu au bout de 10 min'; exit 1\""

say "4. forcer la régénération du KEPUB (celui en place est périmé)"
run "ssh cigogne \"rm -f \\\"\\\$HOME/data/$RELPATH/\\\"*.kepub; \
     sqlite3 \\\$HOME/data/metadata.db \\\"DELETE FROM data WHERE book=$BOOKID AND format='KEPUB';\\\"\""

say "5. réveiller la liseuse : bump des dates + purge de kobo_synced_books"
# ⚠ books_update_trg appelle title_sort() : la fonction doit être enregistrée sur la
#   connexion, sinon « no such function: title_sort ». D'où python et non sqlite3.
# ⚠ timestamp ET last_modified : sans le bump de timestamp la Kobo reçoit un
#   ChangedEntitlement et ne retélécharge pas (mesuré le 21/05/2026). Le doute du
#   04/09 sur la perte d'annotations a été levé le soir même (manche 3) : elles
#   survivent au NewEntitlement, la lecture qui disait le contraire portait sur une
#   base SQLite en mode WAL, donc périmée.
run "ssh cigogne \"python3 -c \\\"
import sqlite3, datetime, re
db = sqlite3.connect('/home/ubuntu/data/metadata.db')
db.create_function('title_sort', 1, lambda t: (lambda m: t[m.end():] + ', ' + m.group(1) if m else t)(re.match(r'^(A|An|The|Le|La|Les|Un|Une|Des)\\\\s+', t or '', re.I)))
now = datetime.datetime.now(datetime.timezone.utc).isoformat(sep=' ')
db.execute('UPDATE books SET timestamp=?, last_modified=? WHERE id=?', (now, now, $BOOKID))
db.commit()
print('   dates portées à', now)
\\\"\""
run "ssh cigogne \"docker exec calibre-web sqlite3 /config/app.db \\\"DELETE FROM kobo_synced_books WHERE book_id=$BOOKID;\\\"\""
run "ssh cigogne \"curl -s -o /dev/null -w '   reconnect HTTP %{http_code}\\n' http://127.0.0.1:8083/reconnect\""

say "6. contrôle — compter DEUX tours de 2 min pour la régénération du KEPUB"
ssh cigogne "ls -la \"\$HOME/data/$RELPATH/\" | sed -n '2,9p'; \
  sqlite3 \$HOME/data/metadata.db \"SELECT format,uncompressed_size FROM data WHERE book=$BOOKID;\""
