#!/usr/bin/env python3
"""
recompose.py — Recompose un volume depuis le témoin complet, quand la copie n'est pas récupérable
(721, Les Vacances : la copie Gutenberg est un abrégé). Décision de Benoît du 19/09/2026 : « Repartir
de Wikisource » — texte de Wikisource (Hachette 1884, transcription relue), contrôlé mot à mot sur
Gallica (Hachette 1861), dans l'enveloppe de la copie (métadonnées, feuille de style, couverture,
pages de titre et dédicace).

Mécanique (celle de restitue.py, appliquée au livre entier) :
  - base Wikisource ; Gallica ne l'emporte que sur une faute de lecture de Wikisource (mot hors
    lexique contre une leçon sûre de l'OCR) ou par décision tracée (`721-decisions.json`) ;
  - légendes d'illustrations écartées ; lettrines (premier mot de chapitre privé de sa capitale
    dans Wikisource) rétablies ; notes de bas de page reprises de Gallica (Wikisource n'en garde
    que l'appel) ; noms de locuteurs, tirets et titres composés comme dans la copie ;
  - chaque chapitre tracé (sous-page Wikisource, vues Gallica).

Usage : python3 recompose.py 721 [--analyse]
"""
import sys, os, re, json, html, zipfile, argparse, subprocess, tempfile, shutil, hashlib, glob
from collections import Counter, defaultdict
import chemins

sys.path.insert(0, chemins.TOOLS)
sys.path.insert(0, f'{chemins.W}/outils')
import collate
from restitue import (ws_paragraphs, ws_tokens, Alto, wc_map, divergences, texte_para, nom_locuteur,
                      formes_noms, legendes_gallica, typo, esc, vue_de, romain, vol_info, CONV, ecrit, Copie)

W = chemins.W
TOOLS = chemins.TOOLS
OUT = f'{chemins.OUT}/propositions/721-abrege'
EPUBCHECK = chemins.EPUBCHECK
SP = '/tmp/claude-1001/-home-ubuntu-src-bp/66382645-7672-486e-9711-0a440b5a0f54/scratchpad/moi'


def notes_gallica(gtxt):
    """Notes de bas de page de l'édition Gallica, par vue : {vue: {numéro: texte}}."""
    res = defaultdict(dict)
    for m in re.finditer(r'#### vue (\d+)\n(.*?)(?=#### vue|\Z)', gtxt, re.S):
        for n in re.finditer(r'(?m)^\s*(\d)\s*[.,]\s+(.{3,300}?)\s*$', m.group(2)):
            res[int(m.group(1))][n.group(1)] = n.group(2).strip()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--analyse', action='store_true')
    a = ap.parse_args()
    i = a.id
    v = vol_info(i)
    conv = dict(CONV[i]); conv['tiret'] = '—'
    base = f'Comtesse-de-Segur-{v["slug"]}'
    src_epub = f'{chemins.SAMPLES}/{base}.epub'
    dec_p = f'{OUT}/{i}-decisions.json'
    dec = json.load(open(dec_p)) if os.path.exists(dec_p) else {}
    # Wikisource nettoyé (césures conditionnelles) ; les appels de note « [1] » sont repérés puis ôtés
    raw = open(f'{W}/ws/{i}.txt', encoding='utf-8').read().replace('­', '')
    appels = []
    def appel(m):
        appels.append(m.group(1))
        return f'⁂{len(appels)}⁂'
    raw = re.sub(r'\[(\d)\]', appel, raw)
    os.makedirs(SP, exist_ok=True)
    wsp = f'{SP}/{i}-ws-propre.txt'
    open(wsp, 'w').write(raw.replace('⁂', ' ⁂ ').replace('  ⁂', ' ⁂'))
    open(wsp, 'w').write(raw)
    paras = ws_paragraphs(wsp)
    # titre de chapitre sans numéro (« ARRIVÉE. » en tête de sous-page) : c'est le titre, le numéro est celui de la sous-page
    prec = None
    for p in paras:
        if p['chap'] != prec and p['chap'] and p['chap'].isdigit() and p['texte'].isupper() and len(p['texte']) < 80:
            p['nature'] = 'titre'
            p['numero'] = romain(int(p['chap']))
        prec = p['chap']
    # nom de locuteur en capitales sans point final (« SOPHIE ») : Wikisource l'écrit parfois ainsi
    for p in paras:
        t = p['texte']
        if p['nature'] == 'corps' and len(t) < 60 and re.match(r"^[A-ZÀÂÄÇÉÈÊËÎÏÔÖÛÙÜŸŒÆ][A-ZÀÂÄÇÉÈÊËÎÏÔÖÛÙÜŸŒÆ’' .\-]+(?:, [a-zàâäçéèêëîïôöûùüÿœæ’' ,\-]+)?\.?$", t) \
                and not re.fullmatch(r'FIN\.?', t):
            p['nature'] = 'locuteur'
    for p in paras:                      # l'appel de note n'est pas un mot : hors de l'alignement
        p['appels'] = [(m.group(1), ' '.join(re.findall(r"[^\s]+", p['texte'][:m.start()])[-3:]))
                       for m in re.finditer(r'⁂(\d+)⁂', p['texte'])]
        p['texte'] = re.sub(r'⁂\d+⁂', '', p['texte'])
    Wt = ws_tokens(paras, conv)
    ark = v['gallica']['ark']
    gtxt = open(f'{W}/gallica/{ark}.txt', encoding='utf-8').read()
    G = collate.aligned(collate.load_witness(f'{W}/gallica/{ark}.txt'))
    gops = collate.align(Wt, G)
    gal = collate.Alignment(Wt, G, gops)
    wc = wc_map(G, Alto(ark))
    copie = Copie(src_epub)
    lex = collate.Lexicon(f'{TOOLS}/lexicon-fr.txt.gz', copie.toks)
    caps = legendes_gallica(gtxt)
    noms = formes_noms(copie)
    dv = divergences(Wt, G, gops, 0, len(Wt), lex, wc, paras, caps, 'ws')
    forces = {(str(d['vue']), d['ws'], d['gallica']): d for d in dec.get('decisions', [])}
    for d in dv:
        f = forces.get((str(d['vue']), d['ws'], d['gallica']))
        if f:
            d['choix'], d['raison'], d['force'] = f['choix'], f.get('raison', ''), True
            for k in ('rendu', 'etendre'):
                if k in f:
                    d[k] = f[k]
        if d['choix'] == 'gallica' and 'rendu' not in d:
            d['rendu'] = typo(' '.join(t.s for t in G[d['b1']:d['b2']]))
    cnt = Counter((d['classe'], d['choix']) for d in dv)
    print('divergences :', dict(cnt))
    if a.analyse:
        for d in dv:
            if d['classe'] in ('variante', 'ajout gallica', 'omission gallica', 'légende') or d['choix'] == 'gallica':
                print(f'  [{d["classe"]} → {d["choix"]}{" (forcé)" if d.get("force") else ""}] vue {d["vue"]} wc {d["wc"]} : '
                      f'ws « {d["ws"]} » / gallica « {d["gallica"]} » — {d["contexte"]}')
        return
    # ---- composition, chapitre par chapitre
    notes_g = notes_gallica(gtxt)
    lettrines = dec.get('lettrines', {})
    par_idx = defaultdict(list)
    for j, t in enumerate(Wt):
        par_idx[t.para].append(j)
    chapitres, cur, locuteur, n_note = [], None, None, 0
    notes_log, lettr_log = [], []
    for p in paras:
        if p['chap'] in (None, 'Préface'):
            continue
        if p['nature'] == 'titre' and p.get('numero'):
            if locuteur is not None and cur is not None:     # nom resté sans réplique : gardé tel quel
                cur['blocs'].append(nom_locuteur(locuteur['texte'], conv, noms) + '.')
                locuteur = None
            cur = {'chap': p['chap'], 'numero': p['numero'], 'titre': p['texte'], 'blocs': [], 'vues': set(), 'notes': []}
            chapitres.append(cur)
            continue
        if cur is None or p['n'] not in par_idx:
            continue
        idx = par_idx[p['n']]
        if p['nature'] == 'locuteur':
            locuteur = p
            continue
        txt = texte_para(p, Wt, idx, dv)
        txt = re.sub(r'^—\s+', '—', txt)
        if not cur['blocs'] and p['chap'] in lettrines:          # lettrine perdue par la transcription
            avant, apres = lettrines[p['chap']]
            if txt.startswith(avant):
                txt = apres + txt[len(avant):]
                lettr_log.append(f'{cur["numero"]} : « {avant}… » → « {apres}… »')
        vs = sorted({vue_de(g) for j in idx if not gal.uncovered[j] for g in G[gal.jstart[j]:gal.jend[j]] if vue_de(g)})
        cur['vues'] |= set(vs)
        # notes : appels de Wikisource, texte de la note pris en bas de la page Gallica
        for na, prefixe in p['appels']:
            num = appels[int(na) - 1]
            texte_note = next((notes_g[x][num] for x in (vs[-1:] + [vs[-1] + 1 if vs else 0]) if x in notes_g and num in notes_g[x]), None) if vs else None
            if len(dec.get('notes', [])) > n_note:      # notes relues : dans l'ordre des appels, texte de Gallica corrigé
                texte_note = dec['notes'][n_note]['texte']
                vs = [dec['notes'][n_note]['vue']]
            n_note += 1
            cur['notes'].append((n_note, texte_note))
            notes_log.append(f'{cur["numero"]} : note {num} → ' + (f'« {texte_note} » (Gallica, vue {vs[-1]})' if texte_note else 'texte introuvable dans Gallica'))
            pre = re.sub(r'⁂\d+⁂', '', prefixe)
            k = txt.find(pre) if pre else -1
            if k < 0:                    # typographie changée : chercher sur le dernier mot seul
                dernier = pre.split(' ')[-1] if pre else ''
                k = txt.find(dernier); pre = dernier
            if k >= 0:
                txt = txt[:k + len(pre)] + f'⟦{n_note}⟧' + txt[k + len(pre):]
            else:
                txt += f'⟦{n_note}⟧'
        if locuteur:
            txt = nom_locuteur(locuteur['texte'], conv, noms) + conv['sep'] + txt
            locuteur = None
        cur['blocs'].append(txt)
    # ---- enveloppe : documents de la copie
    z = zipfile.ZipFile(src_epub)
    docs = [d for d in copie.segments]
    textes = [d for d in docs if 'wrap' not in d]
    raw0 = z.read(textes[0]).decode('utf-8')
    m0 = re.search(r'<p\b[^>]*margin-top: 2em[^>]*>\s*I\.\s', raw0)
    front = raw0[raw0.index('<body'):m0.start()]
    front = front[front.index('>') + 1:]
    # table des matières du livre, refaite
    def titre_phrase0(t):
        mots = [noms.get(m, m) for m in t.rstrip('.').lower().split(' ')]
        x = ' '.join(mots)
        return x[:1].upper() + x[1:]
    lignes_t = [f'{c["numero"]}. ' + esc(typo(titre_phrase0(c['titre']))) for c in chapitres]
    for fc in dec.get('liminaires', []):           # pages liminaires de la copie : fautes que les deux témoins corrigent
        assert front.count(fc['chercher']) == 1, fc
        front = front.replace(fc['chercher'], fc['remplacer'])
    front = re.sub(r'(>Table des matières</p>\s*<p[^>]*>)(.*?)(</p>)', lambda m: m.group(1) + '<br/>\n'.join(lignes_t) + m.group(3),
                   front, count=1, flags=re.S)
    taille = [sum(len(b) for b in c['blocs']) for c in chapitres]
    cible, groupes, acc, g_ = sum(taille) / len(textes), [[] for _ in textes], 0, 0
    for k, c in enumerate(chapitres):
        if acc > cible * (g_ + 1) and g_ < len(textes) - 1:
            g_ += 1
        groupes[g_].append(c)
        acc += taille[k]

    def titre_phrase(t):
        """« NAUFRAGE DE SOPHIE. » → « Naufrage de Sophie » : casse de phrase, noms propres gardés."""
        mots = t.rstrip('.').lower().split(' ')
        mots = [noms.get(m, m) for m in mots]
        x = ' '.join(mots)
        return x[:1].upper() + x[1:]

    def compose(c):
        out = [f'<p style="margin-top: 2em">{c["numero"]}. {esc(typo(titre_phrase(c["titre"])))}.</p>']
        for b in c['blocs']:
            b = esc(b)
            b = re.sub(r'⟦(\d+)⟧', lambda m: f'<sup><a href="#note-{m.group(1)}" id="appel-{m.group(1)}">{m.group(1)}</a></sup>', b)
            out.append(f'<p>{b}</p>')
        for n_, t_ in c['notes']:
            t_ = re.sub(r'\*(.+?)\*', r'<i>\1</i>', esc(typo(t_ or '[note de l’édition, texte non retrouvé]')))
            out.append(f'<p class="note" id="note-{n_}"><a href="#appel-{n_}">{n_}</a>. {t_}</p>')
        return '\n'.join(out)

    neufs = {}
    for k, d in enumerate(textes):
        rawd = z.read(d).decode('utf-8')
        head = rawd[:rawd.index('<body')]
        body_tag = re.search(r'<body[^>]*>', rawd).group(0)
        corps = (front if k == 0 else '') + '\n'.join(compose(c) for c in groupes[k])
        neufs[d] = head + body_tag + '\n' + corps + '\n</body>\n</html>\n'
    os.makedirs(OUT, exist_ok=True)
    dst = f'{OUT}/{base}.recompose.epub'
    with zipfile.ZipFile(dst + '.tmp', 'w') as zo:
        zo.writestr(zipfile.ZipInfo('mimetype'), z.read('mimetype'), compress_type=zipfile.ZIP_STORED)
        for n in z.namelist():
            if n != 'mimetype':
                zo.writestr(n, neufs[n].encode('utf-8') if n in neufs else z.read(n), compress_type=zipfile.ZIP_DEFLATED)
    os.replace(dst + '.tmp', dst)
    r = subprocess.run(['java', '-jar', EPUBCHECK, dst], capture_output=True, text=True)
    m = re.search(r'Messages: (\d+) fatals? / (\d+) errors? / (\d+) warnings?', r.stdout + r.stderr)
    ec = {'fatals': int(m.group(1)), 'erreurs': int(m.group(2)), 'avertissements': int(m.group(3))} if m else {'sortie': (r.stdout + r.stderr)[-1500:]}
    kep = None
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['kepubify', '-o', tmp, dst], capture_output=True, text=True)
        outs = glob.glob(f'{tmp}/*.kepub.epub')
        if outs:
            kep = f'{OUT}/{base}.recompose.kepub.epub'
            shutil.move(outs[0], kep); os.chmod(kep, 0o644)
    mots = sum(len(re.findall(r"[^\W\d_]+", b)) for c in chapitres for b in c['blocs'])
    plan = {'volume': i, 'decision': 'Benoît, 19/09/2026 : « Repartir de Wikisource »',
            'temoins': {'ws': json.load(open(f'{W}/ws/{i}.json')).get('index', {}), 'gallica': {'ark': ark, 'edition': v['gallica']['edition']}},
            'chapitres': [{'numero': c['numero'], 'titre': c['titre'], 'sous_page': c['chap'], 'paragraphes': len(c['blocs']),
                           'vues': [min(c['vues']), max(c['vues'])] if c['vues'] else None, 'notes': c['notes']} for c in chapitres],
            'mots': mots, 'divergences': dv, 'notes': notes_log, 'lettrines': lettr_log,
            'resultat': {'epub': os.path.basename(dst), 'epub_md5': hashlib.md5(open(dst, 'rb').read()).hexdigest(),
                         'epubcheck': ec, 'kepub': os.path.basename(kep) if kep else None}}
    ecrit(f'{OUT}/{i}-recompose.json', json.dumps(plan, ensure_ascii=False, indent=1))
    print(f'{len(chapitres)} chapitres, {mots} mots ; epubcheck {ec} ; kepub {"ok" if kep else "ÉCHEC"}')
    for x in lettr_log + notes_log:
        print('  ', x)


if __name__ == '__main__':
    main()
