import requests
import re
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import yaml

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

DIAS_JANELA = 7  # últimos X dias pra considerar "recente"

# Carrega fontes de sites (YAML externo)
with open("sources_portos.yml", "r", encoding="utf-8") as f:
    SOURCES = yaml.safe_load(f)

# e-mail (vem do Actions via env)
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")
EMAIL_TO = os.getenv("EMAIL_TO_PORTOS")

# -------------------------------------------------
# SUPORTE: parser de datas em PT-BR simples ("29 de outubro de 2025")
# -------------------------------------------------

MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,          # fallback sem acento
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

def parse_data_portugues(texto):
    """
    Tenta achar padrão tipo '29 de outubro de 2025'
    Se achar, devolve datetime(2025,10,29)
    Se não achar, retorna None
    """
    if not texto:
        return None
    texto_low = texto.lower()

    # tenta capturar "DD de <mes> de YYYY"
    m = re.search(r"(\d{1,2})\s+de\s+([a-zçãé]+)\s+de\s+(\d{4})", texto_low)
    if m:
        dia = int(m.group(1))
        mes_nome = m.group(2).replace("ç", "c").replace("ã", "a").replace("é","e")
        ano = int(m.group(3))
        mes_num = MESES.get(mes_nome, None)
        if mes_num:
            try:
                return datetime(ano, mes_num, dia)
            except ValueError:
                pass

    # fallback simples: tenta capturar só ano, se nada
    m2 = re.search(r"(\d{4})", texto_low)
    if m2:
        ano = int(m2.group(1))
        try:
            return datetime(ano, 1, 1)
        except ValueError:
            pass

    return None

# -------------------------------------------------
# SCRAPER MUITO SIMPLES (pegando só HTML bruto)
# -------------------------------------------------

def baixar_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RadarPortuarioBot/1.0; +https://example.com/bot)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.text
        else:
            return ""
    except Exception:
        return ""

# -------------------------------------------------
# EXTRATO DE NOTÍCIAS POR FONTE
# Cada fonte no YAML pode ter:
#   name: "Porto do Itaqui"
#   url: "https://www.portodoitaqui.ma.gov.br/noticias"
#   pattern_item: regex pra blocos de notícia
#   pattern_title, pattern_link, pattern_date: regex dentro do bloco
#
# Tudo bem se nem toda fonte tiver data. Aí a gente marca como "sem data".
# -------------------------------------------------

def extrair_noticias(html, fonte_cfg):
    itens = []

    # pega blocos de notícia
    bloco_regex = fonte_cfg.get("pattern_item")
    if not bloco_regex:
        return itens

    blocos = re.findall(bloco_regex, html, flags=re.DOTALL | re.IGNORECASE)

    for bloco in blocos:
        titulo = None
        link = None
        data_txt = None

        # título
        if fonte_cfg.get("pattern_title"):
            m_t = re.search(fonte_cfg["pattern_title"], bloco, flags=re.DOTALL | re.IGNORECASE)
            if m_t:
                # pega primeiro grupo não vazio
                for g in m_t.groups():
                    if g and g.strip():
                        titulo = re.sub(r"\s+", " ", g.strip())
                        break

        # link
        if fonte_cfg.get("pattern_link"):
            m_l = re.search(fonte_cfg["pattern_link"], bloco, flags=re.DOTALL | re.IGNORECASE)
            if m_l:
                for g in m_l.groups():
                    if g and g.strip():
                        raw = g.strip()
                        if raw.startswith("http"):
                            link = raw
                        else:
                            # tenta montar relativo
                            base = fonte_cfg.get("base", "")
                            link = base.rstrip("/") + "/" + raw.lstrip("/")
                        break

        # data
        if fonte_cfg.get("pattern_date"):
            m_d = re.search(fonte_cfg["pattern_date"], bloco, flags=re.DOTALL | re.IGNORECASE)
            if m_d:
                for g in m_d.groups():
                    if g and g.strip():
                        data_txt = g.strip()
                        break

        itens.append({
            "titulo": titulo or "(sem título)",
            "link": link or fonte_cfg.get("url", ""),
            "data_txt": data_txt or "",
        })

    return itens

# -------------------------------------------------
# FILTRAR ITENS RECENTES
# -------------------------------------------------

def filtrar_recentes(itens, dias=DIAS_JANELA):
    """
    Marca item como recente se a data encontrada (ou None) for
    dentro da janela desejada. Se não tiver data nenhuma,
    deixamos passar assim mesmo (porque alguns sites não publicam a data).
    """
    recentes = []
    hoje = datetime.utcnow()
    limite = hoje - timedelta(days=dias)

    for item in itens:
        data_txt = item.get("data_txt", "")
        data_dt = parse_data_portugues(data_txt)

        if data_dt is None:
            # sem data -> mantém
            recentes.append(item)
        else:
            if data_dt >= limite:
                recentes.append(item)

    return recentes

# -------------------------------------------------
# MONTAR HTML DO E-MAIL
# -------------------------------------------------

def montar_email_html(todas_fontes, dias=DIAS_JANELA):
    style = """
    <style>
      bod
