import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ---------------------------------
# CONFIGURAÇÃO
# ---------------------------------

# quantos dias atrás a gente considera "recente"
DIAS_JANELA = 7

# fontes que vamos monitorar
FONTES = [
    {
        "nome": "Porto do Itaqui - Notícias",
        "url": "https://www.portodoitaqui.ma.gov.br/noticias",
        "tipo": "lista_cards",
        # mapeamento de CSS para tentar extrair título, link e data
        "selectors": {
            "item": ".noticia, .card-noticia, article, .post",
            "titulo": ["h2", "h3", ".titulo", ".title", ".card-title"],
            "link": ["a"],
            "data": [".data", ".post-date", "time", ".dt", ".published"]
        },
        "formato_data": [
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y"
        ],
        "force_domain": "https://www.portodoitaqui.ma.gov.br"
    },
    {
        "nome": "Porto de Santos - Notícias",
        "url": "https://www.portodesantos.com.br/noticias/",
        "tipo": "lista_cards",
        "selectors": {
            "item": ".noticia, article, .post, .card",
            "titulo": ["h2", "h3", ".entry-title", ".titulo"],
            "link": ["a"],
            "data": [".data", "time", ".entry-date"]
        },
        "formato_data": [
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%Y-%m-%d"
        ],
        "force_domain": "https://www.portodesantos.com.br"
    },
    {
        "nome": "Porto de Suape - Notícias",
        "url": "https://www.suape.pe.gov.br/noticias",
        "tipo": "lista_cards",
        "selectors": {
            "item": ".noticia, article, .post, .blog-item, .card-noticia",
            "titulo": ["h2", "h3", ".titulo", ".card-title", ".post-title"],
            "link": ["a"],
            "data": [".data", ".post-date", "time", ".published"]
        },
        "formato_data": [
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%Y-%m-%d"
        ],
        "force_domain": "https://www.suape.pe.gov.br"
    },
    {
        "nome": "ANTAQ - Notícias",
        "url": "https://www.gov.br/antaq/pt-br/assuntos/noticias",
        "tipo": "lista_cards",
        "selectors": {
            "item": "article, .item",
            "titulo": ["h2", "h3", ".titulo", ".title"],
            "link": ["a"],
            "data": [".documentByLine", ".tooltip", "time", ".published"]
        },
        "formato_data": [
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%Y-%m-%d"
        ],
        "force_domain": "https://www.gov.br"
    }
]


# ---------------------------------
# FUNÇÕES DE SUPORTE
# ---------------------------------

def normalizar_data(texto_data, formatos):
    """
    Tenta interpretar uma string de data usando vários formatos.
    Se não conseguir, retorna None.
    """
    if not texto_data:
        return None

    texto_data = texto_data.strip()
    # remove prefixos comuns
    for prefix in ["Publicado em", "Publicada em", "Postado em", "Postado:", "Publicado:", "Data:", "Em:"]:
        if texto_data.lower().startswith(prefix.lower()):
            texto_data = texto_data[len(prefix):].strip()

    # tenta cada formato conhecido
    for fmt in formatos:
        try:
            return datetime.strptime(texto_data, fmt).date()
        except Exception:
            continue

    # tenta heurísticas simples, ex: "27/10/2025 - 10:30"
    # tenta recortar só a parte antes do espaço com hora
    pedacos = texto_data.split()
    if len(pedacos) >= 1:
        bruto = pedacos[0]
        for fmt in formatos:
            try:
                return datetime.strptime(bruto, fmt).date()
            except Exception:
                pass

    return None


def extrair_primeiro(sel_list, parent):
    """
    Dada uma lista de seletores CSS possíveis, retorna o texto (ou href se for <a>) do primeiro que existir.
    """
    if not sel_list:
        return None
    for css in sel_list:
        el = parent.select_one(css)
        if el:
            # se for link e tiver href, devolve href
            if el.name == "a" and el.get("href"):
                return el.get("href").strip()
            # senão devolve texto
            txt = el.get_text(" ", strip=True)
            if txt:
                return txt
    return None


def construir_url_absoluta(href, base):
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    # se veio "/noticia/abc", junta com domínio base
    return base.rstrip("/") + "/" + href.lstrip("/")


def coletar_noticias(fonte):
    """
    Faz request no site, tenta raspar cards de notícia e retorna lista de dicts:
    {
        'titulo': ...,
        'link': ...,
        'data': date|None,
        'fonte': ...
    }
    """
    noticias = []

    try:
        resp = requests.get(fonte["url"], timeout=20, headers={
            "User-Agent": "Mozilla/
