#!/usr/bin/env python3
"""Genera la web estática de La Cuarta Piel a partir del contenido exportado de Cargo.

Uso:  python3 build.py   (lee src/, escribe site/)
"""
import json, re, os, shutil, html, urllib.parse as up
from bs4 import BeautifulSoup
from PIL import Image

SRC = '/home/claude/src'
OUT = '/home/claude/site'

d = json.load(open(f'{SRC}/data.json'))
P = json.load(open(f'{SRC}/pins.json'))
pages = d['pages']
imap = d['imageMap']
FRONT = d['frontSlugs']

# ---------------------------------------------------------------- imágenes
os.makedirs(f'{OUT}/img', exist_ok=True)
IMG = {}  # cargo url -> dict(src, w, h, small)

def process_image(url):
    if url in IMG:
        return IMG[url]
    rel = imap.get(url)
    if not rel:
        return None
    srcp = f'{SRC}/{rel}'
    name = os.path.basename(rel)
    dst = f'{OUT}/img/{name}'
    im = Image.open(srcp)
    w, h = im.size
    if not os.path.exists(dst):
        shutil.copyfile(srcp, dst)
    small = None
    if w > 1000 and name.lower().endswith(('.jpg', '.jpeg', '.png')) and not getattr(im, 'is_animated', False):
        base, ext = os.path.splitext(name)
        sname = f'{base}-800{".jpg"}'
        sdst = f'{OUT}/img/{sname}'
        if not os.path.exists(sdst):
            im2 = im.convert('RGB') if im.mode not in ('RGB',) else im
            if im.mode in ('RGBA', 'LA', 'P'):
                bg = Image.new('RGB', im.size, (255, 255, 255))
                rgba = im.convert('RGBA')
                bg.paste(rgba, mask=rgba.split()[3])
                im2 = bg
            im2.thumbnail((800, 800 * h // w))
            im2.save(sdst, 'JPEG', quality=82, optimize=True, progressive=True)
        small = sname
    IMG[url] = dict(src=name, w=w, h=h, small=small)
    return IMG[url]


def img_tag(soup, url, alt='', sizes='100vw'):
    info = process_image(url)
    t = soup.new_tag('img')
    if not info:
        t['src'] = url
        return t
    t['src'] = 'img/' + info['src']
    if info['small']:
        t['srcset'] = f"img/{info['small']} 800w, img/{info['src']} {info['w']}w"
        t['sizes'] = sizes
    t['width'] = str(info['w'])
    t['height'] = str(info['h'])
    t['alt'] = alt
    t['loading'] = 'lazy'
    t['decoding'] = 'async'
    return t

# ---------------------------------------------------------------- enlaces

def fix_href(href):
    if not href:
        return href
    if href == 'Front-page':
        return './'
    if re.match(r'^(https?:|mailto:|tel:|#|/)', href):
        return href
    return href  # slug relativo -> slug.html servido como /slug

# ---------------------------------------------------------------- galerías

def convert_gallery(soup, g):
    cfg = json.loads(up.unquote(g.get('data-gallery', '%7B%7D')))
    mode = cfg.get('path', 'grid')
    data = cfg.get('data', {})
    cols = int(data.get('columns', 1) or 1)
    md = data.get('mobile_data', {}) or {}
    mcols = int(data.get('responsive_columns') or md.get('columns') or cols)
    pad = float(data.get('image_padding', data.get('responsive_image_padding', 0.5)) or 0)
    captions = data.get('captions', True)
    items = []
    for el in g.find_all(['a', 'img'], recursive=True):
        if el.name == 'img' and el.parent.name == 'a' and el.parent in [x[0] for x in items]:
            continue
        if el.name == 'a':
            im = el.find('img')
            if not im:
                continue
            items.append((el, im))
        elif el.name == 'img' and not (el.parent and el.parent.name == 'a'):
            items.append((None, el))
    box = soup.new_tag('div')
    box['class'] = ['gallery', f'gallery-{mode}']
    box['style'] = f'--cols:{cols};--mcols:{mcols};--pad:{pad}rem'
    sizes = f'(max-width: 768px) {round(100 / mcols)}vw, {round(60 / cols)}vw'
    for a, im in items:
        url = (im.get('data-src') or im.get('src') or '').split('?')[0]
        cap = im.get('data-caption') or ''
        fig = soup.new_tag('figure')
        info = process_image(url)
        if mode == 'justify' and info:
            ar = info['w'] / info['h']
            fig['style'] = f'flex-grow:{ar:.4f};flex-basis:{ar * 14:.2f}rem'
        t = img_tag(soup, url, alt=html.unescape(im.get('alt') or cap), sizes=sizes)
        if a is not None:
            link = soup.new_tag('a', href=fix_href(a.get('href')))
            if a.get('target'):
                link['target'] = a['target']
            link.append(t)
            fig.append(link)
        else:
            fig.append(t)
        if captions and cap:
            fc = soup.new_tag('figcaption')
            if a is not None:
                l2 = soup.new_tag('a', href=fix_href(a.get('href')))
                l2.string = cap
                fc.append(l2)
            else:
                fc.string = cap
            fig.append(fc)
        box.append(fig)
    g.replace_with(box)


def convert_html(src_html):
    soup = BeautifulSoup(src_html, 'html.parser')
    for g in soup.find_all('div', class_='image-gallery'):
        convert_gallery(soup, g)
    for im in soup.find_all('img'):
        if im.get('data-src'):
            url = im['data-src'].split('?')[0]
            new = img_tag(soup, url, alt=im.get('alt', ''))
            im.replace_with(new)
    for a in soup.find_all('a'):
        if a.get('href'):
            a['href'] = fix_href(a['href'])
        if a.get('rel') == ['history'] or a.get('rel') == 'history':
            del a['rel']
        if a.get('target') == '_blank':
            a['rel'] = 'noopener'
    for ifr in soup.find_all('iframe'):
        ifr['loading'] = 'lazy'
    return str(soup)

# ---------------------------------------------------------------- CSS local

def scoped_css(scope, css):
    """Traduce el CSS local de Cargo a reglas con ámbito [data-ls=scope]."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = css.replace('[data-predefined-style="true"]', '')
    css = re.sub(r'\[local-style="\d+"\]', '', css)
    out = []
    for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        body = body.strip()
        if not body or not re.search(r'[a-z-]+\s*:', body):
            continue
        sel = sel.strip()
        targets = []
        for s in sel.split(','):
            s = s.strip()
            if s in ('body', '.backdrop', '.page_background', '.page'):
                if s == '.page' and 'min-height' in body:
                    targets.append(f'[data-ls="{scope}"]')
                continue
            if s == '.container_width':
                targets.append(f'[data-ls="{scope}"]')
            elif s == '.container':
                targets.append(f'[data-ls="{scope}"]')
            elif s == '.content_padding' or s == 'bodycopy':
                targets.append(f'[data-ls="{scope}"] .content')
            elif s.startswith('bodycopy '):
                targets.append(f'[data-ls="{scope}"] .content ' + s[len('bodycopy '):])
            else:
                targets.append(f'[data-ls="{scope}"] .content {s}')
        if targets:
            body = re.sub(r'\s+', ' ', body)
            out.append(f'{", ".join(targets)} {{ {body} }}')
    return '\n'.join(out)


def container_flags(css):
    left = bool(re.search(r'\.container\s*\{[^}]*margin-left:\s*0', css))
    return 'align-left' if left else 'align-right'

# ---------------------------------------------------------------- bio: dibujo

def marker_svg():
    p = '/tmp/claude-tool-results/e0bcfc32-af6f-57f9-8b05-07bfab5cf35e/toolu_01GX6bqk2SjyEaN4iSmL583F-bc026317.json'
    if not os.path.exists(p):
        return ''
    t = json.load(open(p))[0]['text']
    info = json.loads(t[t.index('BEGINSVG') + 8:t.index('ENDSVG')])
    svg = info['svg']
    s = BeautifulSoup(svg, 'html.parser')
    g = s.find('g')
    gt = [float(x) for x in re.findall(r'-?[\d.]+', g['transform'])]
    gx, gy = gt[0], gt[1]
    lines = []
    xs, ys = [], []
    for pl in s.find_all('polyline'):
        m = [float(x) for x in re.findall(r'-?[\d.e]+', pl.get('transform', 'matrix(1,0,0,1,0,0)'))]
        a, b, c, dd, e, f = m if len(m) == 6 else (1, 0, 0, 1, 0, 0)
        pts = []
        for x, y in re.findall(r'(-?[\d.]+),(-?[\d.]+)', pl['points']):
            x, y = float(x), float(y)
            X = a * x + c * y + e + gx
            Y = b * x + dd * y + f + gy
            pts.append((X, Y)); xs.append(X); ys.append(Y)
        sw = float(pl.get('stroke-width', 4)) * a
        lines.append((pts, sw))
    if not xs:
        return ''
    pad = 10
    x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    body = ''.join(
        f'<polyline points="{" ".join(f"{x - x0:.1f},{y - y0:.1f}" for x, y in pts)}" stroke-width="{sw:.2f}"/>'
        for pts, sw in lines)
    return (f'<svg class="marker" viewBox="0 0 {x1 - x0:.0f} {y1 - y0:.0f}" xmlns="http://www.w3.org/2000/svg" '
            f'fill="none" stroke="#000" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="la cuarta piel">'
            f'{body}</svg>')

# ---------------------------------------------------------------- plantilla

GLOBAL = {g['url']: g for g in P['__global']}

def pin_block(pin, scope_id, extra_cls=''):
    po = pin['po']
    cls = ['pin']
    if po.get('exclude_mobile'):
        cls.append('only-desktop')
    if po.get('exclude_desktop'):
        cls.append('only-mobile')
    if po.get('overlay') and po.get('fixed'):
        cls.append('pin-fixed')
        cls.append('pin-' + po.get('position', 'top'))
    cls.append(container_flags(pin['css']))
    if extra_cls:
        cls.append(extra_cls)
    return (f'<div class="{" ".join(cls)}" data-ls="{scope_id}"><div class="content">'
            f'{convert_html(pin["html"])}</div></div>'), scoped_css(scope_id, pin['css'])


def render_page(slug, title, main_html, main_css_raw, page_id, pins, active=None, extra_head='', body_cls=''):
    css_parts = [scoped_css(str(page_id), main_css_raw)]
    top, bottom, fixed = [], [], []
    for pin in pins:
        blk, c = pin_block(pin, str(pin['id']))
        css_parts.append(c)
        po = pin['po']
        if po.get('overlay') and po.get('fixed'):
            fixed.append(blk)
        elif po.get('position') == 'bottom':
            bottom.append(blk)
        else:
            top.append(blk)
    # navegación global
    nav = GLOBAL['Barra-izquierda-navegacion']
    menu = GLOBAL['Bio-contacto-instagram']
    mob = GLOBAL['Mobile-header']
    nav_html = convert_html(nav['html'])
    menu_html = convert_html(menu['html'])
    if active:
        menu_html = menu_html.replace(f'href="{active}"', f'href="{active}" class="active"')
    page_css = '\n'.join(c for c in css_parts if c)
    align = container_flags(main_css_raw)
    full_title = 'La Cuarta Piel' if slug == 'index' else f'{title} — La Cuarta Piel'
    desc = 'La Cuarta Piel: colectivo que explora las intersecciones entre el diseño, la investigación y la mediación.'
    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{desc}">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="preload" href="fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="style.css">
<style>
{page_css}
</style>{extra_head}
</head>
<body class="{body_cls}">
<header class="site-nav only-desktop">
  <div class="logo">{nav_html}</div>
  <nav class="menu">{menu_html}</nav>
</header>
<header class="site-nav-mobile only-mobile">
  <div class="logo">{convert_html(mob['html'])}</div>
  <nav class="menu">{menu_html}</nav>
</header>
<main>
{''.join(top)}
<div class="page {align}" data-ls="{page_id}"><div class="content">
{main_html}
</div></div>
{''.join(bottom)}
</main>
{''.join(fixed)}
</body>
</html>
'''

# ---------------------------------------------------------------- generar

def write(name, content):
    with open(f'{OUT}/{name}', 'w', encoding='utf-8') as f:
        f.write(content)

os.makedirs(f'{OUT}/fonts', exist_ok=True)

# portada
fp = pages['Front-page']
write('index.html', render_page('index', 'La Cuarta Piel', convert_html(fp['content']),
                                fp['page_options']['local_css'], fp['id'], [], body_cls='home'))

# proyectos
for slug in FRONT:
    p = pages[slug]
    pins = P.get(slug, {}).get('pins', [])
    write(f'{slug}.html', render_page(slug, p['title_no_html'] or slug, convert_html(p['content']),
                                     p['page_options']['local_css'], p['id'], pins, body_cls='project'))

# bio
b = pages['bio-1']
svg = open(f'{SRC}/bio-marker.svg').read() if os.path.exists(f'{SRC}/bio-marker.svg') else ''
write('bio-1.html', render_page('bio-1', 'bio', f'<div class="bio-marker">{svg}</div>' + convert_html(b['content']),
                                b['page_options']['local_css'], b['id'], [], active='bio-1', body_cls='bio'))
# contacto
c = pages['contacto']
write('contacto.html', render_page('contacto', 'contacto', convert_html(c['content']),
                                   c['page_options']['local_css'], c['id'], [], active='contacto', body_cls='contacto'))

# 404 -> portada
write('404.html', '<!DOCTYPE html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/"><title>La Cuarta Piel</title><a href="/">la cuarta piel</a>')
print('páginas:', len(FRONT) + 4, 'imágenes:', len(IMG))
