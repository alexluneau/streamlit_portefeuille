
import streamlit as st
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import numpy as np
import json

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    pwd = st.text_input("Mot de passe", type="password")
    if pwd == st.secrets["auth"]["password"]:
        st.session_state.auth = True
        st.experimental_rerun()
    else:
        st.stop()

# Configuration
st.set_page_config(page_title='Dashboard Portefeuille', layout='wide')
st.title('📊 Suivi Avancé de Mon Portefeuille')

# Valeurs de conversion
EUR_USD = yf.download("EURUSD=X", period="1d")["Close"].iloc[-1]
CHF_EUR = yf.download("CHFEUR=X", period="1d")["Close"].iloc[-1]

# Fonctions utilitaires
def to_float(val):
    try:
        return float(val)
    except:
        return np.nan

def signal_rsi(val: float) -> str:
    if pd.isna(val): return '—'
    if val < rsi_oversold: return '📈 Achat'
    if val > rsi_overbought: return '📉 Vente'
    return '⚠️ Neutre'

def strategy_combined(rsi_signal: str, macd_signal: str) -> str:
    if rsi_signal == '📈 Achat' and macd_signal == '📈 Achat':
        return '📈 Achat confirmé'
    elif rsi_signal == '📉 Vente' and macd_signal == '📉 Vente':
        return '📉 Vente confirmée'
    elif rsi_signal == '📈 Achat' and macd_signal == '📉 Vente':
        return '⚠️ Achat anticipé'
    elif rsi_signal == '📉 Vente' and macd_signal == '📈 Achat':
        return '⚠️ Vente anticipée'
    elif rsi_signal == '⚠️ Neutre' and macd_signal == '📉 Vente':
        return '↘️ Tendance baissière'
    elif rsi_signal == '⚠️ Neutre' and macd_signal == '📈 Achat':
        return '↗️ Tendance haussière'
    else:
        return '—'


def signal_macd(m: float, s: float) -> str:
    if pd.isna(m) or pd.isna(s): return '—'
    return '📈 Achat' if m > s else '📉 Vente'

def safe_format_num(fmt):
    return lambda x: fmt.format(x) if (isinstance(x, (int, float)) and not pd.isna(x)) else ''

@st.cache_data(ttl=3600)
def get_data(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period='3mo', auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=3600)
def get_currency_conversion_factor(ticker: str) -> float:
    try:
        currency = yf.Ticker(ticker).info.get("currency", "EUR")
        if currency == "USD": return 1 / EUR_USD
        if currency == "CHF": return CHF_EUR
        return 1.0
    except:
        return 1.0

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df['RSI'] = ta.rsi(df['Close'], length=rsi_length)
    macd = ta.macd(df['Close'], fast=macd_fast, slow=macd_slow, signal=macd_signal)
    if macd is not None and not macd.empty:
        macd.columns = ['MACD', 'MACD_Hist', 'MACD_Signal']
        df = df.join(macd)
    else:
        df[['MACD','MACD_Hist','MACD_Signal']] = np.nan
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    return df

def render_section(items: list):
    rows = []
    charts = []

    crypto_prefixes = {}

    for item in items:
        ticker = item.get('ticker')
        name = item.get('name', ticker)
        qty = item.get('qty', 1)
        df = get_data(ticker)
        conversion = get_currency_conversion_factor(ticker)

        if df.empty:
            price = price_eur = rsi = mval = msig = np.nan
        else:
            df_last = compute_indicators(df).tail(1).squeeze()
            price = to_float(df_last.get('Close'))
            price_eur = to_float(price * conversion)
            rsi = to_float(df_last.get('RSI'))
            mval = to_float(df_last.get('MACD'))
            msig = to_float(df_last.get('MACD_Signal'))

            df_ind = compute_indicators(df)
            charts.append((name, df_ind[['Close', 'SMA20', 'SMA50']]))

        # Déduction de la devise
        if ticker.endswith("-USD") or ticker.split("-")[0] in crypto_prefixes:
            currency = "USD"
        elif ticker.endswith(".PA") or ticker.endswith(".MI") or ticker.startswith(("FR", "NL")):
            currency = "EUR"
        elif ticker.endswith(".SW") or ticker.startswith("CH"):
            currency = "CHF"
        else:
            try:
                currency = yf.Ticker(ticker).info.get("currency", "EUR")
            except Exception as e:
                st.warning(f"Erreur en récupérant la devise pour {ticker} : {e}")
                currency = "EUR"

        value = to_float(price_eur * qty)
        rsi_sig = signal_rsi(rsi)
        macd_sig = signal_macd(mval, msig)
        strategy = strategy_combined(rsi_sig, macd_sig)

        rows.append({
            'Nom': name,
            'Ticker': ticker,
            'Quantité': qty,
            'Prix (Devise)': price,
            'Devise': currency,
            'Valeur (€)': value,
            f'RSI ({rsi_length})': rsi,
            'Signal RSI': rsi_sig,
            f'MACD ({macd_fast},{macd_slow},{macd_signal})': mval,
            'Signal MACD': macd_sig,
            'Stratégie combinée': strategy
        })

    df_table = pd.DataFrame(rows)

    if 'Valeur (€)' in df_table:
        total = df_table['Valeur (€)'].sum()
        total_row = {k: '' for k in df_table.columns}
        total_row['Nom'] = 'Total'
        total_row['Valeur (€)'] = total
        df_table = pd.concat([df_table, pd.DataFrame([total_row])], ignore_index=True)

    for col in ['Quantité', 'Prix (Devise)', 'Valeur (€)', f'RSI ({rsi_length})', f'MACD ({macd_fast},{macd_slow},{macd_signal})']:
        df_table[col] = pd.to_numeric(df_table[col], errors='coerce')

    return df_table, charts



# Chargement JSON
st.sidebar.header("Portefeuille")
portfolio_text = st.sidebar.text_area(
    "Entrez votre portefeuille en JSON",
    value=st.secrets["portfolio"]["json"],
    height=200
)

try:
    default_portfolio = st.secrets["portfolio"]["json"]
    portfolio = json.loads(default_portfolio)
    actions = portfolio.get('actions', [])
    cryptos = portfolio.get('cryptos', [])
except json.JSONDecodeError:
    st.sidebar.error("JSON invalide.")
    actions = []
    cryptos = []


# Paramètres techniques
st.sidebar.subheader("Paramètres Techniques")
rsi_length = st.sidebar.number_input("RSI périodes", 2, 50, 14)
rsi_oversold = st.sidebar.number_input("RSI survente (<)", 1, 100, 30)
rsi_overbought = st.sidebar.number_input("RSI surachat (>)", 1, 100, 70)
macd_fast = st.sidebar.number_input("MACD rapide", 1, 50, 12)
macd_slow = st.sidebar.number_input("MACD lente", 1, 100, 26)
macd_signal = st.sidebar.number_input("MACD signal", 1, 50, 9)

# Affichage des tableaux
st.header("📋 Aperçu du Portefeuille")
actions_df, actions_charts = render_section(actions)
cryptos_df, cryptos_charts = render_section(cryptos)

st.subheader("📄 Actions")
st.dataframe(actions_df.style.format({
    'Quantité': safe_format_num("{:.2f}"),
    'Prix (Devise)': safe_format_num("{:.2f}"),
    'Valeur (€)': safe_format_num("{:.2f}"),
    f'RSI ({rsi_length})': safe_format_num("{:.1f}"),
    f'MACD ({macd_fast},{macd_slow},{macd_signal})': safe_format_num("{:.2f}")
}))

st.subheader("🪙 Cryptomonnaies")
st.dataframe(cryptos_df.style.format({
    'Quantité': safe_format_num("{:.4f}"),
    'Prix': safe_format_num("{:.2f}"),
    'Valeur (€)': safe_format_num("{:.2f}"),
    f'RSI ({rsi_length})': safe_format_num("{:.1f}"),
    f'MACD ({macd_fast},{macd_slow},{macd_signal})': safe_format_num("{:.2f}")
}))

# Graphiques
st.header("📈 Graphiques Techniques")
for name, chart_data in actions_charts + cryptos_charts:
    st.subheader(f'📊 {name}')
    st.line_chart(chart_data)

# Graphique global portefeuille
all_series = []
for item in actions + cryptos:
    ticker = item.get('ticker')
    qty = item.get('qty', 1)
    df = get_data(ticker)
    if df.empty: continue
    conversion = get_currency_conversion_factor(ticker)
    s = df['Close'] * qty * conversion
    s.name = item.get('name', ticker)
    all_series.append(s)

if all_series:
    combined = pd.concat(all_series, axis=1).ffill()
    total_value = combined.sum(axis=1).to_frame('Total')
    st.header('💰 Évolution de la valeur totale du portefeuille')
    st.line_chart(total_value)

# Générer un prompt ChatGPT basé sur le portefeuille
st.header("🧠 Analyse assistée par ChatGPT")

# Construire les lignes pour chaque actif
def build_prompt(actions_df, cryptos_df):
    def format_line(row):
        nom = row['Nom']
        ticker = row['Ticker']
        valeur = safe_format_num("{:.2f}")(row['Valeur (€)'])
        rsi = row.get('Signal RSI', '—')
        macd = row.get('Signal MACD', '—')
        return f"- {nom} ({ticker}) : {row['Quantité']} unités (~{valeur} €), RSI = {rsi}, MACD = {macd}"

    lines_actions = [format_line(row) for _, row in actions_df.iterrows() if row['Nom'] != 'Total']
    lines_cryptos = [format_line(row) for _, row in cryptos_df.iterrows() if row['Nom'] != 'Total']

    prompt = f"""
Tu es un expert en analyse de portefeuille boursier et cryptomonnaies, spécialisé en indicateurs techniques.

Je te fournis ci-dessous mon portefeuille actuel avec les indicateurs RSI et MACD pour chaque actif.

### Ta mission :
1. Pour chaque actif : indique s’il faut **acheter**, **conserver** ou **vendre**, et justifie ta réponse en t’appuyant sur les indicateurs RSI et MACD.
2. Si possible, ajoute une remarque sur la tendance actuelle ou les perspectives.
3. S’il existe actuellement une **forte opportunité d’achat** sur un autre actif (actions ou cryptos), **signale-la à la fin** et explique pourquoi.

---

Voici mes positions actuelles :

### Actions
{chr(10).join(lines_actions)}

### Cryptomonnaies
{chr(10).join(lines_cryptos)}

Merci de m’indiquer tes recommandations avec clarté.
""".strip()
    return prompt

# Génération et affichage
prompt_final = build_prompt(actions_df, cryptos_df)
st.subheader("📋 Prompt à copier pour ChatGPT")
st.code(prompt_final, language="markdown")
