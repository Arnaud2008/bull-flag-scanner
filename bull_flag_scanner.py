"""
Bull Flag Scanner — S&P 500 + NASDAQ 100 + Dow Jones
Detecte : uptrend fort + consolidation + breakout avec volume
Version 7 — Detection flag par fenetre glissante sur prix
"""

import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ============================================================
#  CONFIGURATION — Variables d'environnement (GitHub Secrets)
# ============================================================

EMAIL_EXPEDITEUR   = os.environ.get("EMAIL_EXPEDITEUR", "arnaudlalancette08@gmail.com")
EMAIL_MOT_DE_PASSE = os.environ.get("EMAIL_MOT_DE_PASSE", "")
EMAIL_DESTINATAIRE = os.environ.get("EMAIL_DESTINATAIRE", "arnaudlalancette08@gmail.com")

# --- Criteres du setup ---
# (v4 : assouplis pour capturer plus de vrais bull flags)
CONSOL_JOURS_MIN   = 4      # Avant: 5  — quelques flags forment vite
CONSOL_JOURS_MAX   = 40     # Avant: 30 — flags plus longs aussi valides
ATR_BAISSE_PCT     = 15     # Avant: 20 — baisse de volatilite moins stricte
VOL_BAISSE_PCT     = 20     # Avant: 30 — baisse de volume moins stricte
BREAKOUT_PCT       = 1.0    # Avant: 2.0 — les grosses caps cassent souvent avec +1%
VOL_MULT_BREAKOUT  = 1.5    # Avant: 1.8 — grosses caps ont moins de spikes de volume
IMPULSION_PCT_MIN  = 8      # Avant: 15 — 8% sur AAPL = mouvement tres fort
IMPULSION_PCT_MAX  = 100    # Avant: 60 — inclut les breakouts explosifs
IMPULSION_JOURS    = 45     # Avant: 30 — flag pole peut se former plus lentement
MA20_DESSUS        = True   # Garder — filtre les downtrends
MA50_DESSUS        = False  # Avant: True — assoupli, permet les rebounds

# ============================================================
#  LISTE COMPLETE : S&P 500 + NASDAQ 100 + DOW JONES
#  (~550 tickers uniques apres deduplication)
# ============================================================

SP500 = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB","AKAM",
    "ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN","AMCR","AEE",
    "AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH","ADI","ANSS","AON",
    "APA","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG","AIZ","T","ATO","ADSK","AZO",
    "AVB","AVY","AXON","BKR","BALL","BAC","BBWI","BAX","BDX","WRB","BRK-B","BBY",
    "BIO","TECH","BIIB","BLK","BX","BA","BMY","AVGO","BR","BRO","BF-B","BLDR",
    "BSX","CHRW","CDNS","CZR","CPT","CPB","COF","CAH","KMX","CCL","CARR","CTLT","CAT",
    "CBOE","CBRE","CDW","CE","COR","CNC","CNP","CF","CRL","SCHW","CHTR","CVX","CMG",
    "CB","CHD","CI","CINF","CTAS","CSCO","C","CFG","CLX","CME","CMS","KO","CTSH",
    "CL","CMCSA","CAG","COP","ED","STZ","CEG","COO","CPRT","GLW","CPAY","CTVA","CSGP",
    "COST","CTRA","CRWD","CCI","CSX","CMI","CVS","DHR","DRI","DVA","DAY","DECK","DE",
    "DAL","DVN","DXCM","FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV","DOW","DHI",    "DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW","EA","ELV","EMR","ENPH",
    "ETR","EOG","EPAM","EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG","ES",
    "EXC","EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX","FIS",
    "FITB","FSLR","FE","FI","FLT","FMC","F","FTNT","FTV","FOXA","FOX","BEN","FCX",
    "GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM","GPC","GILD","GPN",
    "GL","GDDY","GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HES","HPE","HLT",
    "HOLX","HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX",
    "IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF","IP","IPG","INTU","ISRG","IVZ",
    "INVH","IQV","IRM","JBHT","JBL","JKHY","J","JNJ","JCI","JPM","JNPR","K","KVUE",
    "KDP","KEY","KEYS","KMB","KIM","KMI","KLAC","KHC","KR","LHX","LH","LRCX","LW",
    "LVS","LDOS","LEN","LLY","LIN","LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB",
    "MRO","MPC","MKTX","MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT",
    "MRK","META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP",
    "MDLZ","MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX","NEM",
    "NWSA","NWS","NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG","NUE","NVDA",
    "NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR","PKG","PANW",
    "PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG","PM","PSX","PNW","PNC","POOL",
    "PPG","PPL","PFG","PG","PGR","PLD","PRU","PEG","PTC","PSA","PHM","QRVO","PWR",
    "QCOM","DGX","RL","RJF","RTX","O","REG","REGN","RF","RSG","RMD","RVTY","ROK",
    "ROL","ROP","ROST","RCL","SPGI","CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG",
    "SWKS","SJM","SW","SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE","SYK",
    "SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL","TDY",
    "TFX","TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB","TFC",
    "TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL","UPS","URI","UNH","UHS","VLO",
    "VTR","VLTO","VRSN","VRSK","VZ","VRTX","VTRS","VICI","V","VST","VMC","WAB",
    "WMT","WM","WAT","WEC","WFC","WELL","WST","WDC","WY","WHR","WMB","WTW","GWW",
    "WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS"
]

NASDAQ100_EXTRA = [
    "ADSK","AEP","AMAT","AMD","AMGN","ANSS","ASML","BKNG","CDNS","CDW","CEG",
    "CHTR","CPRT","CSGP","CSCO","CTAS","CTSH","DDOG","DLTR","DXCM","EA","ENPH",
    "EXC","FAST","FTNT","GEHC","GFS","HON","IDXX","INTC","INTU","ISRG",
    "KDP","KLAC","LRCX","LULU","MAR","MCHP","MDLZ","MELI","MNST","MRNA","MSFT",
    "MU","NFLX","NXPI","ODFL","ON","ORLY","PANW","PAYX","PCAR","PDD","PEP",
    "QCOM","REGN","ROST","SBUX","SNPS","TEAM","TMUS","TSLA","TXN","VRSK",
    "VRTX","WBD","WDAY","XEL","ZS","ZM","OKTA","CRWD","DDOG","NET","SNOW",
    "PLTR","RBLX","COIN","HOOD","AFRM","UPST","SOFI","RIVN","LCID","NIO","XPEV",
    "LI","GRAB","SEA","BIDU","JD","PDD","TCOM","BILI"
]

DOW30 = [
    "AAPL","AMGN","AXP","BA","CAT","CRM","CSCO","CVX","DIS","DOW",
    "GS","HD","HON","IBM","INTC","JNJ","JPM","KO","MCD","MMM",
    "MRK","MSFT","NKE","PG","TRV","UNH","V","VZ","WMT","AMZN"
]

# Deduplication
TOUS_TICKERS = list(dict.fromkeys(SP500 + NASDAQ100_EXTRA + DOW30))

# ============================================================
#  LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler()]
)

# ============================================================
#  FONCTIONS
# ============================================================

def nettoyer_serie(s):
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

        logging.info(f"    {ticker} passe breakout+volume : +{changement_pct:.1f}% / vol {ratio_vol:.1f}x")

        # -----------------------------------------------------------
        # DETECTION DU FLAG — Approche par prix (plus robuste)
        #
        # Principe : on cherche une fenetre de N jours AVANT aujourd'hui
        # ou le prix s'est consolide dans un range etroit (flag plat).
        #
        # On teste toutes les fenetres de 4 a CONSOL_JOURS_MAX jours
        # en partant d'hier vers le passe, et on garde la meilleure.
        # -----------------------------------------------------------

        meilleure_consol = None

        # Tester des fenetres de consolidation de longueur variable
        for duree in range(CONSOL_JOURS_MIN, min(CONSOL_JOURS_MAX + 1, len(df) - 15)):
            # La fenetre se termine a iloc[-2] (hier, avant le breakout)
            fin   = len(df) - 2          # index hier
            debut = fin - duree          # index debut de la fenetre

            if debut < 10:
                break

            zone = df.iloc[debut:fin]
            if len(zone) < CONSOL_JOURS_MIN:
                continue

            z_high = float(zone["High"].max())
            z_low  = float(zone["Low"].min())
            if z_low == 0:
                continue

            # Range total de la zone en %
            z_range_pct = (z_high - z_low) / z_low * 100

            # Un bon flag = range < 10% (consolidation serree)
            if z_range_pct > 12.0:
                continue

            # Verifier baisse ATR vs les 10 jours AVANT la zone
            avant = df.iloc[max(debut - 10, 0) : debut]
            if len(avant) < 3:
                continue
            atr_avant   = float(avant["ATR"].mean())
            atr_pendant = float(zone["ATR"].mean())
            if atr_avant == 0 or pd.isna(atr_avant) or pd.isna(atr_pendant):
                continue
            baisse_atr = (1 - atr_pendant / atr_avant) * 100

            # Verifier baisse volume
            vol_avant   = float(avant["Volume"].mean())
            vol_pendant = float(zone["Volume"].mean())
            if vol_avant == 0:
                continue
            baisse_vol = (1 - vol_pendant / vol_avant) * 100

            # Garder si les criteres sont remplis
            if baisse_atr >= ATR_BAISSE_PCT and baisse_vol >= VOL_BAISSE_PCT:
                meilleure_consol = {
                    "duree"      : duree,
                    "range_pct"  : z_range_pct,
                    "baisse_atr" : baisse_atr,
                    "baisse_vol" : baisse_vol,
                    "debut_idx"  : debut,
                    "zone"       : zone,
                }
                break   # On prend la plus courte fenetre valide

        if meilleure_consol is None:
            # Log pour comprendre pourquoi — tester la fenetre de 5j par defaut
            fin   = len(df) - 2
            debut = fin - 5
            zone5 = df.iloc[debut:fin]
            z_h = float(zone5["High"].max())
            z_l = float(zone5["Low"].min())
            z_r = (z_h - z_l) / z_l * 100 if z_l > 0 else 0
            avant5 = df.iloc[max(debut - 10, 0) : debut]
            if len(avant5) >= 3:
                a_atr = float(avant5["ATR"].mean())
                p_atr = float(zone5["ATR"].mean())
                b_atr = (1 - p_atr / a_atr) * 100 if a_atr > 0 else 0
                a_vol = float(avant5["Volume"].mean())
                p_vol = float(zone5["Volume"].mean())
                b_vol = (1 - p_vol / a_vol) * 100 if a_vol > 0 else 0
                logging.info(f"    {ticker} elimine : meilleure fenetre 5j — range={z_r:.1f}% atr_baisse={b_atr:.1f}% vol_baisse={b_vol:.1f}%")
            else:
                logging.info(f"    {ticker} elimine : pas de consolidation valide trouvee")
            return None

        nb_jours_consol = meilleure_consol["duree"]
        zone_consol     = meilleure_consol["zone"]
        consol_debut_idx = meilleure_consol["debut_idx"]
        baisse_atr_pct  = meilleure_consol["baisse_atr"]
        baisse_vol_pct  = meilleure_consol["baisse_vol"]

        logging.info(f"    {ticker} flag OK : {nb_jours_consol}j, range={meilleure_consol['range_pct']:.1f}%, atr-{baisse_atr_pct:.0f}%, vol-{baisse_vol_pct:.0f}%")

        debut_imp = df.iloc[max(consol_debut_idx - IMPULSION_JOURS, -len(df)) : consol_debut_idx]
        if len(debut_imp) < 5:
            return None

        prix_bas      = float(debut_imp["Low"].min())
        prix_haut     = float(df.iloc[consol_debut_idx]["High"])
        impulsion_pct = (prix_haut - prix_bas) / prix_bas * 100
        if not (IMPULSION_PCT_MIN <= impulsion_pct <= IMPULSION_PCT_MAX):
            logging.info(f"    {ticker} elimine : impulsion hors range ({impulsion_pct:.1f}%, requis {IMPULSION_PCT_MIN}-{IMPULSION_PCT_MAX}%)")
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
        # Supprime les erreurs de tickers delistes pour garder les logs propres
        msg = str(e)
        if "delisted" not in msg.lower() and "no data found" not in msg.lower():
            logging.warning(f"{ticker} — erreur : {e}")
        return None


def lancer_scan():
    date_heure = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info(f"=== Debut du scan — {date_heure} ===")
    logging.info(f"Nombre de tickers a analyser : {len(TOUS_TICKERS)}")

    setups = []

    for i, ticker in enumerate(TOUS_TICKERS, 1):
        logging.info(f"  [{i}/{len(TOUS_TICKERS)}] {ticker}...")
        resultat = analyser_stock(ticker)
        if resultat:
            setups.append(resultat)
            logging.info(f"  *** SETUP TROUVE : {ticker} ***")

    logging.info(f"=== Fin du scan — {len(setups)} setup(s) trouves ===")

    if setups:
        envoyer_email(setups, date_heure)
    else:
        logging.info("Aucun setup — pas d'email envoye.")


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
    <p><strong>{len(setups)} setup(s)</strong> detecte(s) sur S&P 500 + NASDAQ 100 + Dow Jones</p>
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
#  POINT D'ENTREE
# ============================================================

if __name__ == "__main__":
    logging.info("Bull Flag Scanner v7 demarre.")
    lancer_scan()
