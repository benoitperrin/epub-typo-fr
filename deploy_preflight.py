#!/usr/bin/env python3
"""
deploy_preflight.py — Ce qu'un déploiement va coûter aux annotations. À appeler
AVANT de remplacer un livre de la bibliothèque.

Une passe typographique déplace les koboSpan : kepubify ne coupe pas une phrase
après « … », et l'insécable posée entre « ! » et « » » supprime la frontière. Les
ids sont alors RÉATTRIBUÉS, et un surlignage glisse en silence vers la phrase
voisine. Mesuré : de 45 % à 83 % d'ancres intactes selon les livres.

Le serveur ne sait rien des surlignages (l'API Kobo de calibre-web n'implémente que
la position de lecture) : c'est le registre alimenté par kobo_moisson.py qui le dit.

  deploy_preflight.py --registre R.json --uuid <uuid du livre>
                      --kepub-actuel actuel.kepub --epub-nouveau nouveau.epub

Sortie : 0 = rien en jeu, on peut déployer.
         3 = le livre est annoté ET des ancres bougent — décision humaine.
"""
import sys, os, re, json, argparse, subprocess, tempfile, shutil, zipfile, html, unicodedata

SPAN = re.compile(r'<span class="koboSpan" id="(kobo\.[\d.]+)">(.*?)</span>', re.S)
KEPUBIFY = shutil.which('kepubify') or os.path.expanduser('~/bin/kepubify')


def cle(t):
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    for a, b in (('’', "'"), ('…', '...'), ('—', '-'), ('«', '"'), ('»', '"'), ('œ', 'oe')):
        t = t.replace(a, b)
    return re.sub(r'\s+', '', t).lower()


def carte(kepub):
    z, out = zipfile.ZipFile(kepub), {}
    for n in sorted(x for x in z.namelist() if x.lower().endswith(('.htm', '.html', '.xhtml'))):
        h = z.read(n).decode('utf-8', 'replace')
        for m in SPAN.finditer(h):
            out[(n.split('/')[-1], m.group(1))] = cle(html.unescape(re.sub('<[^>]+>', '', m.group(2))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--registre', required=True)
    ap.add_argument('--uuid', required=True)
    ap.add_argument('--kepub-actuel', required=True)
    ap.add_argument('--epub-nouveau', required=True)
    a = ap.parse_args()

    try:
        reg = json.load(open(a.registre))
    except Exception as e:
        print('⚠ registre illisible (%s) — on ne sait donc PAS si ce livre est annoté.' % e)
        print('  Brancher une liseuse et lancer kobo_moisson.py, ou passer outre en connaissance de cause.')
        return 3

    notes = [x for x in reg.get('annotations', []) if x.get('uuid') == a.uuid]
    liseuses = {x['liseuse']: reg['liseuses'].get(x['liseuse'], {}).get('nom') or x['liseuse']
                for x in notes}
    vus = ', '.join('%s (vu le %s)' % (v.get('nom') or k, (v.get('vu') or '?')[:10])
                    for k, v in reg.get('liseuses', {}).items())
    print('registre : %d annotation(s) sur ce livre — liseuses connues : %s' % (len(notes), vus or 'aucune'))
    if not notes:
        print('✅ aucune annotation connue sur ce livre : rien en jeu.')
        return 0

    print('   porteurs : %s' % ', '.join(sorted(liseuses.values())))
    if not os.path.exists(a.kepub_actuel):
        print('⚠ KEPUB actuel introuvable : impossible de mesurer. Décision humaine.')
        return 3

    out = tempfile.mkdtemp()
    r = subprocess.run([KEPUBIFY, '-o', out, a.epub_nouveau], capture_output=True, text=True)
    faits = os.listdir(out)
    if not faits:
        shutil.rmtree(out, ignore_errors=True)
        print('⚠ kepubify a échoué (%s) : impossible de mesurer.' % r.stderr.strip()[:80])
        return 3
    av, ap_ = carte(a.kepub_actuel), carte(os.path.join(out, faits[0]))
    shutil.rmtree(out, ignore_errors=True)

    # ce qui compte n'est pas le taux global, mais le sort des ancres RÉELLEMENT portées
    touchees = []
    for x in notes:
        fich = x['content_id'].split('!')[-1].split('/')[-1]
        sid = (x['debut'] or '').replace('span#', '').replace('\\', '')
        k = (fich, sid)
        if k not in ap_:
            touchees.append((x, 'ancre morte'))
        elif k in av and av[k] != ap_[k]:
            touchees.append((x, 'glissement : l’ancre lira un autre texte'))
    intactes = len(notes) - len(touchees)
    print('   ancres du livre : %d intactes, %d à recoller' % (intactes, len(touchees)))
    for x, why in touchees[:6]:
        print('     • %-22s %s — « %s »' % (x['debut'], why, re.sub(r'\s+', ' ', x['texte'])[:44]))
    if not touchees:
        print('✅ les annotations portées sur ce livre survivent telles quelles.')
        return 0
    print('🔴 %d annotation(s) vont glisser. Déployer reste possible — le recollage se fait'
          % len(touchees))
    print('   ensuite, liseuse branchée : kobo_reancre.py <KoboReader.sqlite> --apres <kepub> --go')
    return 3


if __name__ == '__main__':
    sys.exit(main())
