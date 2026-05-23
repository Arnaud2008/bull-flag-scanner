"""
Bull Flag Scanner — S&P 500
Detecte : uptrend fort + consolidation + breakout avec volume
Version 2 — compatible yfinance recent
"""

import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import schedule
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ============================================================
#  CONFIGURATION — MODIFIE CES VALEURS
# ============================================================

EMAIL_EXPEDITEUR   = "arnaudlalancette08@gmail.com"
EMAIL_MOT_DE_PASSE = "dkkv jsty zurf vrap"
EMAIL_DESTINATAIRE = "arnaudlalancette08@gmail.com"

# --- Criteres du setup ---
CONSOL_JOURS_MIN   = 5
CONSOL_JOURS_MAX   = 30
ATR_BAISSE_PCT     = 20
VOL_BAISSE_PCT     = 30
BREAKOUT_PCT       = 2.0
VOL_MULT_BREAKOUT  = 1.8
IMPULSION_PCT_MIN  = 15
IMPULSION_PCT_MAX  = 60
IMPULSION_JOURS    = 30
MA20_DESSUS        = True
MA50_DESSUS        = True
SCAN_NB_STOCKS     = 100
HEURE_SCAN         = "13:45"

# ============================================================
#  LISTE S&P 500
# ============================================================

SP500 = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","UNH","JPM",
    "V","XOM","PG","JNJ","MA","HD","CVX","MRK","ABBV","LLY",
    "AVGO","PEP","KO","COST","TMO","MCD","CSCO","WMT","ABT","ACN",
    "CRM","DIS","NFLX","ADBE","TXN","NEE","QCOM","NKE","MDT","BMY",
    "AMGN","LIN","UPS","HON","LOW","GS","PM","SBUX","INTU","AXP",
    "IBM","RTX","CAT","GE","SPGI","BLK","ISRG","GILD","DE","MDLZ",
    "ADI","PLD","MMC","SYK","MU","REGN","ZTS","CI","SO","TJX",
    "DUK","AON","CME","SHW","PYPL","ICE","CL","EQIX","NOC","PGR",
    "ETN","APD","MCO","ORLY","KLAC","HCA","ELV","F","GM","USB",
    "PANW","CRWD","SNOW","DDOG","ANET","MELI","SHOP","SQ","COIN","ROKU"
]

# ============================================================
#  LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("scanner.log"),
        logging.StreamHandler()
    ]
)

# ============================================================
#  FONCTIONS
# ============================================================

def nettoyer_serie(s):
    """Convertit une Series ou DataFrame colonne en Series 1D propre."""
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return pd.Series(s.values.flatten(), index=s.index, dtype=float)


def calcul_atr(df, periode=14):
    high       = nettoyer_serie(df["High"])
    low        = nettoyer_serie(df["Low"])
    close_prev = nettoyer_serie(df["Close"]).shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low  - close_prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(periode).mean()


def analyser_stock(ticker):
    try:
        raw = yf.download(ticker, period="90d", interval="1d",
                          progress=False, auto_adjust=True)
        if raw is None or len(raw) < 60:
            return None

        # Aplatir les colonnes multi-index si present
        df = pd.DataFrame()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in raw.columns:
                df[col] = nettoyer_serie(raw[col])

        if df.empty or len(df) < 60:
            return None

        df["ATR"]   = calcul_atr(df)
        df["MA20"]  = df["Close"].rolling(20).mean()
        df["MA50"]  = df["Close"].rolling(50).mean()
        df["VolMA"] = df["Volume"].rolling(20).mean()

        dernier     = df.iloc[-1]
        prix_actuel = float(dernier["Close"])
        vol_actuel  = float(dernier["Volume"])
        vol_moy     = float(dernier["VolMA"])
        ma20        = float(dernier["MA20"])
        ma50        = float(dernier["MA50"])

        if MA20_DESSUS and prix_actuel < ma20:
            return None
        if MA50_DESSUS and prix_actuel < ma50:
            return None

        hier = df.iloc[-2]
        changement_pct = (prix_actuel - float(hier["Close"])) / float(hier["Close"]) * 100
        if changement_pct < BREAKOUT_PCT:
            return None

        ratio_vol = vol_actuel / vol_moy if vol_moy > 0 else 0
        if ratio_vol < VOL_MULT_BREAKOUT:
            return None

        # Recherche debut consolidation
        consol_debut = None
        for i in range(2, min(CONSOL_JOURS_MAX + 2, len(df) - 5)):
            bougie    = df.iloc[-i]
            range_pct = (float(bougie["High"]) - float(bougie["Low"])) / float(bougie["Low"]) * 100
            if range_pct > 2.0:
                consol_debut = -i
                break

        if consol_debut is None:
            return None

        nb_jours_consol = abs(consol_debut) - 1
        if nb_jours_consol < CONSOL_JOURS_MIN:
            return None

        zone_consol = df.iloc[consol_debut:-1]
        if len(zone_consol) < CONSOL_JOURS_MIN:
            return None

        atr_avant   = float(df.iloc[consol_debut - 5 : consol_debut]["ATR"].mean())
        atr_pendant = float(zone_consol["ATR"].mean())
        if atr_avant == 0:
            return None
        baisse_atr_pct = (1 - atr_pendant / atr_avant) * 100
        if baisse_atr_pct < ATR_BAISSE_PCT:
            return None

        vol_avant   = float(df.iloc[consol_debut - 10 : consol_debut]["Volume"].mean())
        vol_pendant = float(zone_consol["Volume"].mean())
        if vol_avant == 0:
            return None
        baisse_vol_pct = (1 - vol_pendant / vol_avant) * 100
        if baisse_vol_pct < VOL_BAISSE_PCT:
            return None

        debut_imp = df.iloc[max(consol_debut - IMPULSION_JOURS, -len(df)) : consol_debut]
        if len(debut_imp) < 5:
            return None

        prix_bas   = float(debut_imp["Low"].min())
        prix_haut  = float(df.iloc[consol_debut]["High"])
        impulsion_pct = (prix_haut - prix_bas) / prix_bas * 100
        if not (IMPULSION_PCT_MIN <= impulsion_pct <= IMPULSION_PCT_MAX):
            return None

        return {
            "ticker"          : ticker,
            "prix"            : round(prix_actuel, 2),
            "changement_pct"  : round(changement_pct, 2),
            "ratio_vol"       : round(ratio_vol, 2),
            "nb_jours_consol" : nb_jours_consol,
            "baisse_atr_pct"  : round(baisse_atr_pct, 1),
            "baisse_vol_pct"  : round(baisse_vol_pct, 1),
            "impulsion_pct"   : round(impulsion_pct, 1),
            "ma20"            : round(ma20, 2),
            "ma50"            : round(ma50, 2),
        }

    except Exception as e:
        logging.warning(f"{ticker} — erreur : {e}")
        return None


def lancer_scan():
    date_heure = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info(f"=== Debut du scan — {date_heure} ===")

    tickers = SP500[:SCAN_NB_STOCKS]
    setups  = []

    for i, ticker in enumerate(tickers, 1):
        logging.info(f"  Analyse {ticker} ({i}/{len(tickers)})...")
        resultat = analyser_stock(ticker)
        if resultat:
            setups.append(resultat)
            logging.info(f"  SETUP TROUVE : {ticker}")
        time.sleep(0.4)

    logging.info(f"=== Fin du scan — {len(setups)} setup(s) trouves ===")

    if setups:
        envoyer_email(setups, date_heure)
    else:
        logging.info("Aucun setup — pas d email envoye.")


def envoyer_email(setups, date_heure):
    sujet = f"Bull Flag Scanner — {len(setups)} setup(s) — {date_heure}"

    lignes = ""
    for s in setups:
        lignes += f"""
        <tr>
          <td style="padding:10px;font-weight:bold;color:#534AB7">{s['ticker']}</td>
          <td style="padding:10px">${s['prix']}</td>
          <td style="padding:10px;color:#27500A">+{s['changement_pct']}%</td>
          <td style="padding:10px">{s['ratio_vol']}x</td>
          <td style="padding:10px">{s['nb_jours_consol']} j</td>
          <td style="padding:10px">-{s['baisse_atr_pct']}%</td>
          <td style="padding:10px">-{s['baisse_vol_pct']}%</td>
          <td style="padding:10px">+{s['impulsion_pct']}%</td>
        </tr>"""

    corps = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto">
    <h2 style="color:#534AB7">Bull Flag Scanner — {date_heure}</h2>
    <p><strong>{len(setups)} setup(s)</strong> detecte(s) sur le S&P 500</p>
    <table border="0" cellspacing="0" cellpadding="0"
           style="border-collapse:collapse;width:100%;font-size:14px">
      <thead>
        <tr style="background:#534AB7;color:white">
          <th style="padding:10px;text-align:left">Ticker</th>
          <th style="padding:10px;text-align:left">Prix</th>
          <th style="padding:10px;text-align:left">Hausse</th>
          <th style="padding:10px;text-align:left">Vol. BO</th>
          <th style="padding:10px;text-align:left">Consol.</th>
          <th style="padding:10px;text-align:left">ATR baisse</th>
          <th style="padding:10px;text-align:left">Vol. baisse</th>
          <th style="padding:10px;text-align:left">Impulsion</th>
        </tr>
      </thead>
      <tbody>{lignes}</tbody>
    </table>
    <br>
    <p style="color:#888;font-size:11px">Ce ne sont pas des conseils financiers.</p>
    </body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = sujet
        msg["From"]    = EMAIL_EXPEDITEUR
        msg["To"]      = EMAIL_DESTINATAIRE
        msg.attach(MIMEText(corps, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
            serveur.login(EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE)
            serveur.sendmail(EMAIL_EXPEDITEUR, EMAIL_DESTINATAIRE, msg.as_string())

        logging.info(f"Email envoye a {EMAIL_DESTINATAIRE}")

    except Exception as e:
        logging.error(f"Erreur envoi email : {e}")


# ============================================================
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    logging.info("Bull Flag Scanner v2 demarre.")
    logging.info(f"Scan programme tous les jours a {HEURE_SCAN} UTC.")

    lancer_scan()

    schedule.every().day.at(HEURE_SCAN).do(lancer_scan)

    while True:
        schedule.run_pending()
        time.sleep(30)
