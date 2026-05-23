"""
Bull Flag Scanner — S&P 500
Detecte : uptrend fort + consolidation + breakout avec volume
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

EMAIL_EXPEDITEUR  = "arnaudlalancette08@gmail.com"      # Ton adresse Gmail
EMAIL_MOT_DE_PASSE = "dkkv jsty zurf vrap"     # Mot de passe d'application Gmail (16 caracteres)
EMAIL_DESTINATAIRE = "arnaudlalancette08@gmail.com"     # Ou tu veux recevoir les alertes

# --- Criteres du setup ---
CONSOL_JOURS_MIN   = 5       # Consolidation minimum en jours
CONSOL_JOURS_MAX   = 30      # Consolidation maximum en jours
ATR_BAISSE_PCT     = 20      # ATR doit avoir baisse de X% pendant la consolidation
VOL_BAISSE_PCT     = 30      # Volume moyen doit avoir baisse de X% pendant la consolidation
BREAKOUT_PCT       = 2.0     # Hausse minimum du jour de breakout (%)
VOL_MULT_BREAKOUT  = 1.8     # Volume du breakout X fois la moyenne
IMPULSION_PCT_MIN  = 15      # Hausse minimum du "mat du drapeau" (%)
IMPULSION_PCT_MAX  = 60      # Hausse maximum (evite les paraboles deja epuisees)
IMPULSION_JOURS    = 30      # Fenetre pour mesurer l impulsion
MA20_DESSUS        = True    # Prix doit etre au-dessus de la MA20
MA50_DESSUS        = True    # Prix doit etre au-dessus de la MA50
SCAN_NB_STOCKS     = 100     # Nombre de stocks du S&P500 a scanner (max 503)

# Heure du scan (format HH:MM, heure locale de ton serveur)
HEURE_SCAN = "13:45"  # 9h45 ET = 15 min apres ouverture du marche

# ============================================================
#  LISTE S&P 500 (top 100 par capitalisation)
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
#  LOGIQUE DU SCANNER
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("scanner.log"),
        logging.StreamHandler()
    ]
)

def calcul_atr(df, periode=14):
    """Average True Range sur N jours."""
    high = df["High"]
    low  = df["Low"]
    close_prev = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low  - close_prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(periode).mean()


def analyser_stock(ticker):
    """
    Telecharge les donnees et verifie les criteres Bull Flag.
    Retourne un dict avec les details si le setup est valide, sinon None.
    """
    try:
        df = yf.download(ticker, period="90d", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 60:
            return None

        df = df.copy()
        df["ATR"]   = calcul_atr(df)
        df["MA20"]  = df["Close"].rolling(20).mean()
        df["MA50"]  = df["Close"].rolling(50).mean()
        df["VolMA"] = df["Volume"].rolling(20).mean()

        # Prix actuel et dernier jour
        dernier      = df.iloc[-1]
        prix_actuel  = float(dernier["Close"])
        vol_actuel   = float(dernier["Volume"])
        vol_moy      = float(dernier["VolMA"])
        ma20         = float(dernier["MA20"])
        ma50         = float(dernier["MA50"])

        # --- Critere : prix au-dessus des MAs ---
        if MA20_DESSUS and prix_actuel < ma20:
            return None
        if MA50_DESSUS and prix_actuel < ma50:
            return None

        # --- Critere : breakout du jour ---
        hier = df.iloc[-2]
        changement_pct = (prix_actuel - float(hier["Close"])) / float(hier["Close"]) * 100
        if changement_pct < BREAKOUT_PCT:
            return None

        # --- Critere : volume du breakout ---
        ratio_vol = vol_actuel / vol_moy if vol_moy > 0 else 0
        if ratio_vol < VOL_MULT_BREAKOUT:
            return None

        # --- Recherche de la zone de consolidation ---
        # On cherche le debut de la consolidation : le dernier sommet local avant aujourd hui
        # On remonte depuis hier jusqu a trouver une bougie avec un range > seuil
        consol_debut = None
        for i in range(2, min(CONSOL_JOURS_MAX + 2, len(df) - 5)):
            bougie = df.iloc[-i]
            range_pct = (float(bougie["High"]) - float(bougie["Low"])) / float(bougie["Low"]) * 100
            # Si la bougie a un range > 2% on considere que c est la fin de l impulsion
            if range_pct > 2.0:
                consol_debut = -i
                break

        if consol_debut is None:
            return None

        nb_jours_consol = abs(consol_debut) - 1
        if nb_jours_consol < CONSOL_JOURS_MIN:
            return None

        # --- Zone de consolidation ---
        zone_consol = df.iloc[consol_debut:-1]
        if len(zone_consol) < CONSOL_JOURS_MIN:
            return None

        # ATR pendant la consolidation vs ATR avant
        atr_avant_consol  = float(df.iloc[consol_debut - 5 : consol_debut]["ATR"].mean())
        atr_pendant_consol = float(zone_consol["ATR"].mean())
        if atr_avant_consol == 0:
            return None
        baisse_atr_pct = (1 - atr_pendant_consol / atr_avant_consol) * 100

        if baisse_atr_pct < ATR_BAISSE_PCT:
            return None

        # Volume moyen pendant la consolidation
        vol_avant_consol   = float(df.iloc[consol_debut - 10 : consol_debut]["Volume"].mean())
        vol_pendant_consol = float(zone_consol["Volume"].mean())
        if vol_avant_consol == 0:
            return None
        baisse_vol_pct = (1 - vol_pendant_consol / vol_avant_consol) * 100

        if baisse_vol_pct < VOL_BAISSE_PCT:
            return None

        # --- Critere : impulsion avant la consolidation (le "mat") ---
        debut_impulsion = df.iloc[max(consol_debut - IMPULSION_JOURS, -len(df)) : consol_debut]
        if len(debut_impulsion) < 5:
            return None

        prix_bas_impulsion  = float(debut_impulsion["Low"].min())
        prix_haut_impulsion = float(df.iloc[consol_debut]["High"])
        impulsion_pct = (prix_haut_impulsion - prix_bas_impulsion) / prix_bas_impulsion * 100

        if not (IMPULSION_PCT_MIN <= impulsion_pct <= IMPULSION_PCT_MAX):
            return None

        # --- Tout est valide : setup confirme ---
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
    """Scan complet du S&P500 et envoi de l email si des setups sont trouves."""
    date_heure = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info(f"=== Debut du scan — {date_heure} ===")

    tickers = SP500[:SCAN_NB_STOCKS]
    setups  = []

    for i, ticker in enumerate(tickers, 1):
        logging.info(f"  Analyse {ticker} ({i}/{len(tickers)})...")
        resultat = analyser_stock(ticker)
        if resultat:
            setups.append(resultat)
            logging.info(f"  ✅ SETUP TROUVE : {ticker}")
        time.sleep(0.4)  # Evite d etre bloque par Yahoo Finance

    logging.info(f"=== Fin du scan — {len(setups)} setup(s) trouve(s) ===")

    if setups:
        envoyer_email(setups, date_heure)
    else:
        logging.info("Aucun setup — pas d email envoye.")


# ============================================================
#  EMAIL
# ============================================================

def envoyer_email(setups, date_heure):
    """Formate et envoie l email d alerte."""

    sujet = f"🚀 Bull Flag Scanner — {len(setups)} setup(s) — {date_heure}"

    # Corps HTML
    lignes = ""
    for s in setups:
        lignes += f"""
        <tr>
          <td style="padding:10px;font-weight:bold;color:#534AB7">{s['ticker']}</td>
          <td style="padding:10px">${s['prix']}</td>
          <td style="padding:10px;color:#27500A">+{s['changement_pct']}%</td>
          <td style="padding:10px">{s['ratio_vol']}×</td>
          <td style="padding:10px">{s['nb_jours_consol']} j</td>
          <td style="padding:10px">-{s['baisse_atr_pct']}%</td>
          <td style="padding:10px">-{s['baisse_vol_pct']}%</td>
          <td style="padding:10px">+{s['impulsion_pct']}%</td>
        </tr>
        """

    corps = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto">

    <h2 style="color:#534AB7">🚀 Bull Flag Scanner — {date_heure}</h2>
    <p><strong>{len(setups)} setup(s)</strong> detecte(s) sur le S&P 500</p>

    <table border="0" cellspacing="0" cellpadding="0"
           style="border-collapse:collapse;width:100%;font-size:14px">
      <thead>
        <tr style="background:#534AB7;color:white">
          <th style="padding:10px;text-align:left">Ticker</th>
          <th style="padding:10px;text-align:left">Prix</th>
          <th style="padding:10px;text-align:left">Hausse jour</th>
          <th style="padding:10px;text-align:left">Vol. breakout</th>
          <th style="padding:10px;text-align:left">Consol.</th>
          <th style="padding:10px;text-align:left">ATR baisse</th>
          <th style="padding:10px;text-align:left">Vol. baisse</th>
          <th style="padding:10px;text-align:left">Impulsion</th>
        </tr>
      </thead>
      <tbody>
        {lignes}
      </tbody>
    </table>

    <br>
    <p style="color:#888;font-size:12px">
      Criteres : Consol. &ge; {CONSOL_JOURS_MIN}j &bull;
      ATR &darr; {ATR_BAISSE_PCT}%+ &bull;
      Vol. moy. &darr; {VOL_BAISSE_PCT}%+ &bull;
      Breakout &ge; {BREAKOUT_PCT}% &bull;
      Vol. breakout &ge; {VOL_MULT_BREAKOUT}× &bull;
      Impulsion {IMPULSION_PCT_MIN}–{IMPULSION_PCT_MAX}%
    </p>
    <p style="color:#888;font-size:11px">Ce ne sont pas des conseils financiers. Fais toujours ta propre analyse.</p>

    </body></html>
    """

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
#  PLANIFICATEUR
# ============================================================

if __name__ == "__main__":
    logging.info("Bull Flag Scanner demarre.")
    logging.info(f"Scan programme tous les jours a {HEURE_SCAN} (heure serveur).")

    # Lance un premier scan immediat au demarrage (optionnel)
    lancer_scan()

    # Programme le scan quotidien
    schedule.every().day.at(HEURE_SCAN).do(lancer_scan)

    while True:
        schedule.run_pending()
        time.sleep(30)
