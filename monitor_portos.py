import requests
from bs4 import BeautifulSoup
import yaml
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import urllib.parse

# -------------------------
# Configuração geral
# -------------------------

DIAS_JANELA = 14  # últimos 14 dias

# Vamos ler credenciais dos envs que o workflow injeta
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_APP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO_PORTOS", "")

if not (GMAIL_USER and GMAIL_PASS and EMAIL_TO):
    print("⚠️ Credenciais ausentes (GMAIL_USER / GMAIL_APP_PASS / EMAIL_TO_PORTOS).")
    # não damos exit(1) pra você poder testar local sem segredo
    # mas no Actions isso vai acabar falhando no envio de e-mail depois


# -------------------------
# Helpers
# -------------------------

def normalize_space(txt: str) -> str:
    if not txt:
        return ""
    return " ".join(txt.split())


def parse_br_date(date_str):
    """
    Tenta ler datas tipo:
      - '29/10/2025'
      - '29.10.2025'
      - '29-10-2025'
      - '29 de outubro de 2025'
    Se não conseguir, retorna None.
    """
    if not date_str:
        return None

    date_str = date_str.strip().lower()

    # formatos dd/mm/aaaa, dd.mm.aaaa, dd-mm-aaaa
    for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"]:
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass

    # tentar "29 de outubro de 2025"
    meses = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembr
