# monitor_portos.py
import os
import requests
from bs4 import BeautifulSoup
import datetime
import smtplib
import yaml
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

DAYS_PORTO = int(os.getenv('DAYS_PORTO', '2'))
GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_APP_PASS = os.environ['GMAIL_APP_PASS']
EMAIL_TO_PORTOS = os.environ['EMAIL_TO_PORTOS']

EMAIL_SUBJECT = os.getenv('EMAIL_SUBJECT_PORTOS', f'🚢 Radar Portos — últimas {DAYS_PORTO} dias')
USER_AGENT = 'Mozilla/5.0 (compatible; RadarPortuarioBot/1.0)'

def carregar_fontes(yaml_path='sources_portos.yml'):
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def extrair_texto(element, selector_list):
    for sel in selector_list.split(','):
        sel = sel.strip()
        if not sel:
            continue
        found = element.select_one(sel)
        if found:
            txt = found.get_text(strip=True)
            if txt:
                return txt
    return ''

def extrair_link(element, selector_list, base_url):
    for sel in selector_list.split(','):
        sel = sel.strip()
        if not sel:
            continue
        found = element.select_one(sel)
        if found and found.has_attr('href'):
            href = (found['href'] or '').strip()
            if not href:
                continue
            if href.startswith('http://') or href.startswith('https://'):
                return href
            return base_url.rstrip('/') + '/' + href.lstrip('/')
    return ''

def extrair_data(element, selector_list):
    for sel in selector_list.split(','):
        sel = sel.strip()
        if not sel:
            continue
        found = element.select_one(sel)
        if found:
            raw = found.get_text(' ', strip=True)
            if raw:
                return raw
    return ''

def tentar_parse_data_br(texto):
    if not texto:
        return None
    cand = texto.strip().lower()
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            dt = datetime.datetime.strptime(cand, fmt).date()
            return dt
        except Exception:
            pass
    return None

def coletar_noticias(fonte):
    url = fonte['url']
    headers = {'User-Agent': USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')
    blocos = soup.select(fonte['filtro_css'])
    noticias = []
    for bloco in blocos:
        titulo = extrair_texto(bloco, fonte['seletor_titulo'])
        link   = extrair_link(bloco, fonte['seletor_link'], base_url=fonte['url'])
        data_s = extrair_data(bloco, fonte['seletor_data'])
        if not titulo or not link:
            continue
        data_norm = tentar_parse_data_br(data_s)
        noticias.append({'porto': fonte['sigla'], 'titulo': titulo, 'link': link, 'data_site': data_s, 'data_norm': data_norm})
    return noticias

def filtrar_recentes(noticias, days_window):
    hoje = datetime.date.today()
    limite = hoje - datetime.timedelta(days=days_window)
    novas = []
    for n in noticias:
        if n['data_norm'] is None or n['data_norm'] >= limite:
            novas.append(n)
    return novas

def agrupar_por_porto(noticias):
    grupos = {}
    for n in noticias:
        grupos.setdefault(n['porto'], []).append(n)
    for _, lst in grupos.items():
        lst.sort(key=lambda x: x['data_norm'] or datetime.date(1900, 1, 1), reverse=True)
    return grupos

def montar_email_html(grupos, days_window):
    style = '<style>body{font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222}h2{margin:0 0 10px 0}h3{margin:16px 0 6px 0;color:#003366}table{border-collapse:collapse;width:100%;margin-top:6px}th,td{border:1px solid #ddd;padding:8px;vertical-align:top}th{background:#f5f5f5;text-align:left;font-weight:600}.muted{color:#666;font-size:13px}.datecell{white-space:nowrap;font-size:13px;color:#555}</style>'
    head = f'<h2>Radar Portos — últimas {days_window} dias</h2><p class="muted">Monitor automático de notícias institucionais de portos brasileiros (Itaqui, Santos, Suape, Paranaguá, Pecém, Açu). Foco: sustentabilidade, descarbonização, energia, operações e investimentos.</p>'
    blocks = []
    for porto, lst in grupos.items():
        if not lst:
            continue
        rows = []
        for item in lst:
            shown_date = item['data_site'] or ''
            rows.append('<tr><td class="datecell">'+shown_date+'</td><td><a href="'+item['link']+'" target="_blank" rel="noopener noreferrer">'+item['titulo']+'</a></td></tr>')
        bloco_html = f'<h3>{porto}</h3><table><thead><tr><th>Data</th><th>Título / Link</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
        blocks.append(bloco_html)
    blocks_html = '<p>Nenhuma notícia recente encontrada.</p>' if not blocks else ''.join(blocks)
    return '<!DOCTYPE html><html><head>'+style+'</head><body>'+head+blocks_html+'</body></html>'

def montar_email_txt(grupos, days_window):
    out = [f'Radar Portos — últimas {days_window} dias', '']
    for porto, lst in grupos.items():
        out.append(f'== {porto} ==')
        if not lst:
            out.append('  (sem notícias recentes)')
        else:
            for item in lst:
                d = item['data_site'] or ''
                out.append(f'  - [{d}] {item['"'+'titulo'+'"'] }  {item['"'+'link'+'"']}')
        out.append('')
    return '\n'.join(out)

def enviar_email(html_body, txt_body):
    msg = MIMEMultipart('alternative')
    msg['From'] = GMAIL_USER
    msg['To'] = EMAIL_TO_PORTOS
    msg['Subject'] = EMAIL_SUBJECT
    msg.attach(MIMEText(txt_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=45) as s:
        s.starttls()
        s.login(GMAIL_USER, GMAIL_APP_PASS)
        s.send_message(msg)

def main():
    try:
        fontes = carregar_fontes()
    except FileNotFoundError:
        raise SystemExit("Arquivo 'sources_portos.yml' não encontrado na raiz do repositório.")
    todas = []
    for fonte in fontes:
        try:
            noticias_site = coletar_noticias(fonte)
            noticias_filtradas = filtrar_recentes(noticias_site, DAYS_PORTO)
            todas.extend(noticias_filtradas)
        except Exception as e:
            todas.append({'porto': fonte.get('sigla','UNKNOWN'), 'titulo': f'ERRO ao coletar {fonte.get('"'+'nome'+'"','')}: {e}', 'link': fonte.get('url',''), 'data_site': '', 'data_norm': None})
    grupos = agrupar_por_porto(todas)
    html_body = montar_email_html(grupos, DAYS_PORTO)
    txt_body = montar_email_txt(grupos, DAYS_PORTO)
    enviar_email(html_body, txt_body)
    print('✅ Radar Portos enviado com sucesso.')

if __name__ == '__main__':
    main()
