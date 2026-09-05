#!/usr/bin/env python3
"""
kobo_moisson.py — Récolter les annotations d'une Kobo dans un registre durable.

Le serveur ne sait rien des surlignages : l'API Kobo de calibre-web n'implémente
que la position de lecture. Ce savoir ne vit que sur les appareils, et il s'évapore
dès qu'on les débranche — or c'est lui qui dit si un déploiement est risqué.

Ce script le fixe. Branchez une liseuse, lancez-le : il note quelles œuvres portent
des annotations, avec l'ancre et le TEXTE FIGÉ de chacune — de quoi, plus tard,
recoller sans avoir l'appareil sous la main (kobo_reancre.py).

  kobo_moisson.py <KoboReader.sqlite> --registre registre.json [--nom Grégoire]

⚠ La base d'une Kobo est en mode WAL : la copier seule rend un état arbitrairement
ancien. Prendre KoboReader.sqlite ET -wal ET -shm, ou ne lire qu'après un démontage
propre. Le 04/09/2026, l'oubli a fait conclure à tort à une destruction.
"""
import sys, os, re, json, sqlite3, argparse, datetime

UUID = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')


def serie(db_path):
    """Le numéro de série, lu dans .kobo/version à côté de la base."""
    v = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'version')
    try:
        m = re.match(r'(N[0-9A-Za-z]+),', open(v).read())
        return m.group(1) if m else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('db')
    ap.add_argument('--registre', required=True)
    ap.add_argument('--nom', help='à qui est cette liseuse')
    ap.add_argument('--serie', help='numéro de série si version/ est absent')
    a = ap.parse_args()

    # sqlite3.connect() CRÉE une base vide quand le chemin n'existe pas : on
    # récolterait alors zéro annotation sans rien remarquer, et on écraserait dans
    # le registre ce qu'on savait de cette liseuse. Vérifier d'abord.
    if not os.path.isfile(a.db) or os.path.getsize(a.db) == 0:
        sys.exit('base absente ou vide : %s' % a.db)
    sn = a.serie or serie(a.db) or os.path.basename(a.db)
    # WAL : le journal n'est un risque que s'il existe ET porte des transactions.
    wal = a.db + '-wal'
    if os.path.exists(wal) and os.path.getsize(wal) > 0:
        print('⚠ un %s non vide accompagne cette base : lire les trois fichiers '
              'ensemble, sinon l’état lu est arbitrairement ancien.' % os.path.basename(wal),
              file=sys.stderr)
    db = sqlite3.connect(a.db)

    rows = db.execute("""
        SELECT b.BookmarkID, b.VolumeID, b.ContentID, b.StartContainerPath, b.StartOffset,
               b.EndContainerPath, b.EndOffset, b.Text, b.Annotation, b.Type, b.DateCreated,
               c.Title
        FROM Bookmark b LEFT JOIN content c ON c.ContentID = b.VolumeID
        WHERE b.Text IS NOT NULL AND b.Text <> ''""").fetchall()

    try:
        reg = json.load(open(a.registre))
    except Exception:
        reg = {'liseuses': {}, 'annotations': []}

    reg['liseuses'][sn] = {'nom': a.nom or reg['liseuses'].get(sn, {}).get('nom'),
                           'vu': datetime.datetime.now().isoformat(timespec='seconds'),
                           'annotations': len(rows)}
    # on remplace en bloc ce qu'on savait de CETTE liseuse : elle fait autorité
    reg['annotations'] = [x for x in reg['annotations'] if x.get('liseuse') != sn]
    for (bid, vol, cid, sp, so, ep, eo, txt, note, typ, cree, titre) in rows:
        m = UUID.search(vol or '')
        reg['annotations'].append({
            'liseuse': sn, 'bookmark': bid, 'uuid': m.group(1) if m else None,
            'titre': titre, 'content_id': cid, 'debut': sp, 'debut_offset': so,
            'fin': ep, 'fin_offset': eo, 'texte': txt, 'note': note,
            'type': typ, 'cree': cree})

    tmp = a.registre + '.tmp'
    json.dump(reg, open(tmp, 'w'), ensure_ascii=False, indent=1)
    os.replace(tmp, a.registre)

    par_livre = {}
    for x in reg['annotations']:
        par_livre.setdefault(x['uuid'], set()).add(x['liseuse'])
    print('%s (%s) : %d annotation(s) récoltée(s)' % (sn, a.nom or '?', len(rows)))
    print('registre : %d annotation(s), %d œuvre(s), %d liseuse(s) — %s'
          % (len(reg['annotations']), len(par_livre), len(reg['liseuses']), a.registre))


if __name__ == '__main__':
    main()
