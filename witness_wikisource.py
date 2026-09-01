#!/usr/bin/env python3
"""
witness_wikisource.py — Récupère le texte d'une œuvre publiée sur Wikisource (FR par
défaut) pour servir de témoin de collation : chapitres dans l'ordre du sommaire,
en-têtes/pieds de navigation, numéros de page et notes retirés.

Sortie : un fichier texte, un paragraphe par ligne vide, chaque chapitre précédé
d'une ligne « ### <titre de la sous-page> » ; un fichier JSON à côté (édition
déclarée par l'index Livre:, sous-pages, dates de révision).

Usage :
  python3 witness_wikisource.py "Les Malheurs de Sophie" temoin-ws.txt [--lang fr]
        [--index "Ségur - Les Malheurs de Sophie.djvu"] [--pause 0.5]
"""
import sys, re, json, html, time, argparse, urllib.request, urllib.parse

UA = 'epub-typo-fr/collation (https://github.com/benoitperrin/epub-typo-fr)'


def api(lang, **params):
    params.update(format='json', formatversion='2')
    url = f'https://{lang}.wikisource.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=90))
        except Exception as e:                      # réseau : on réessaie
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def parse_html(lang, page):
    d = api(lang, action='parse', page=page, prop='text|revid', disableeditsection=1)
    if 'error' in d:
        return None, None
    return d['parse']['text'], d['parse'].get('revid')


def strip_block(h, open_re):
    """Retire un élément ouvert par `open_re` avec ses descendants (équilibrage des <div>)."""
    out, pos = [], 0
    for m in re.finditer(open_re, h):
        if m.start() < pos:
            continue
        out.append(h[pos:m.start()])
        depth, i = 0, m.start()
        for t in re.finditer(r'<(/?)div\b[^>]*>', h[m.start():]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                i = m.start() + t.end()
                break
        else:
            i = len(h)
        pos = i
    out.append(h[pos:])
    return ''.join(out)


def html_to_text(h):
    h = re.sub(r'<style.*?</style>|<script.*?</script>', '', h, flags=re.S)
    # navigation, en-têtes, blocs non exportés, notes, figures
    for open_re in (r'<div[^>]*(?:id="headertemplate"|id="subheader"|class="[^"]*(?:ws-noexport|headertemplate|footertemplate|reflist|references)[^"]*")[^>]*>',):
        h = strip_block(h, open_re)
    h = re.sub(r'<figure\b.*?</figure>', '', h, flags=re.S)
    h = re.sub(r'<ol class="references">.*?</ol>', '', h, flags=re.S)
    h = re.sub(r'<sup class="reference".*?</sup>', '', h, flags=re.S)
    h = re.sub(r'<span class="pagenum[^>]*>.*?</span>', '', h, flags=re.S)
    h = re.sub(r'<span[^>]*class="[^"]*ws-pagenum[^"]*"[^>]*>.*?</span>', '', h, flags=re.S)
    h = re.sub(r'<(?:p|div|h[1-6]|li|tr|table|blockquote|dd|dt)\b[^>]*>', '\n\n', h)
    h = re.sub(r'<br\s*/?>', '\n', h)
    t = html.unescape(re.sub(r'<[^>]+>', '', h))
    t = t.replace('\xa0', ' ')
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r' *\n *', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def toc_order(main_html, page):
    """Sous-pages dans l'ordre des liens du sommaire de la page principale."""
    prefix = '/wiki/' + page.replace(' ', '_') + '/'
    seen, order = set(), []
    for m in re.finditer(r'href="(/wiki/[^"#]+)"', main_html):
        href = urllib.parse.unquote(m.group(1))
        if not href.startswith(prefix):
            continue
        sub = href[len(prefix):].replace('_', ' ')
        if sub.lower().endswith('texte entier') or sub in seen:
            continue
        seen.add(sub)
        order.append(sub)
    return order


def natural_key(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', s)]


def index_info(lang, index):
    d = api(lang, action='parse', page='Livre:' + index, prop='wikitext')
    if 'error' in d:
        return {}
    wt = d['parse']['wikitext']
    info = {}
    for k in ('Titre', 'Editeur', 'Annee', 'Lieu', 'Source', 'Avancement', 'Fac-similes'):
        m = re.search(r'\|\s*' + k + r'\s*=\s*(.*)', wt)
        if m:
            v = re.sub(r'\{\{Éditeur\|([^}|]+)(?:\|[^}]*)?\}\}', r'\1', m.group(1))
            v = re.sub(r'<[^>]+>|\[\[|\]\]|\{\{|\}\}', '', v).strip()
            info[k] = v.split('|')[0].strip()[:120]
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('page'); ap.add_argument('out')
    ap.add_argument('--lang', default='fr')
    ap.add_argument('--index', help='nom du fichier Livre: (djvu/pdf) pour relever l\'édition')
    ap.add_argument('--pause', type=float, default=0.5)
    args = ap.parse_args()

    main_html, _ = parse_html(args.lang, args.page)
    if main_html is None:
        sys.exit(f'page introuvable : {args.page}')
    order = toc_order(main_html, args.page)
    if not order:
        d = api(args.lang, action='query', list='allpages', apprefix=args.page + '/', aplimit=500)
        order = sorted((p['title'].split('/', 1)[1] for p in d['query']['allpages']
                        if not p['title'].lower().endswith('texte entier')), key=natural_key)
    meta = {'page': args.page, 'lang': args.lang, 'subpages': [], 'index': {}}
    if args.index:
        meta['index'] = index_info(args.lang, args.index)
    chunks = []
    for sub in order:
        title = f'{args.page}/{sub}'
        h, revid = parse_html(args.lang, title)
        time.sleep(args.pause)
        if h is None:
            meta['subpages'].append({'title': title, 'missing': True})
            continue
        t = html_to_text(h)
        meta['subpages'].append({'title': title, 'revid': revid, 'chars': len(t)})
        chunks.append(f'### {sub}\n\n{t}')
        print(f'  {title} : {len(t)} car.', file=sys.stderr)
    with open(args.out, 'w') as f:
        f.write('\n\n'.join(chunks) + '\n')
    with open(re.sub(r'\.txt$', '', args.out) + '.json', 'w') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f'{len(chunks)} sous-pages → {args.out}')


if __name__ == '__main__':
    main()
