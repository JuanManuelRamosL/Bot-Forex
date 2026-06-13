# Bot de Trading Forex v2 — Mean Reversion + Filtro de Régimen

Bot de trading algorítmico en Python que se conecta a OANDA. Hace backtesting con
datos históricos reales y opera automáticamente en cuenta demo.

**Estrategia:** Mean Reversion (Bollinger Bands + RSI) con stop-loss dinámico por ATR.

## Novedades de la v2

1. **Filtro de régimen (ADX):** el bot ya no opera a ciegas. Detecta si el mercado
   está lateral (donde mean reversion funciona) o en tendencia fuerte (donde es
   peligroso), y solo abre trades cuando el mercado está lateral.
2. **Spread real en el backtest:** ahora descuenta el costo del spread en cada
   operación, así los resultados son honestos y no optimistas.
3. **Circuit breaker:** si el bot pierde más de un % configurable en un solo día,
   deja de abrir trades hasta el día siguiente. Protege contra rachas malas.

---

## 1. Requisitos
- Python 3.9+
- Cuenta demo de OANDA (gratis)

## 2. Credenciales OANDA (gratis)
1. Entrá a oanda.com y creá una cuenta **Practice / Demo**.
2. Buscá **"Manage API Access"** y generá un **token**.
3. Anotá tu **Account ID** (formato `101-001-XXXXXXX-001`).

## 3. Instalación
```bash
cd forex-bot-v2
python -m venv venv
# Windows (Git Bash):
source venv/Scripts/activate
# Windows (PowerShell):
# .\venv\Scripts\Activate.ps1
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

## 4. Configuración
Abrí `config.py`, pegá tu token y Account ID, y dejá `OANDA_ENV = "practice"`.
Ahí mismo podés ajustar el filtro de régimen, el spread, y el circuit breaker.

## 5. Backtest (hacelo primero)
```bash
python backtest.py
```

## 6. Bot en vivo (demo)
```bash
python live_bot.py
```
Frenar con `Ctrl + C`.

---

## Parámetros nuevos en config.py

| Parámetro | Qué hace |
|---|---|
| `USE_REGIME_FILTER` | Activa/desactiva el filtro de tendencia |
| `ADX_MAX` | Solo opera si el ADX está por debajo (25 = solo mercados laterales) |
| `SPREAD_PIPS` | Spread por par, descontado en cada trade del backtest |
| `USE_CIRCUIT_BREAKER` | Activa/desactiva el freno diario |
| `MAX_DAILY_LOSS` | % de pérdida diaria que dispara el freno (0.03 = 3%) |

## Archivos
- `config.py` — credenciales y todos los parámetros
- `strategy.py` — indicadores (Bollinger, ATR, RSI, ADX) y lógica de señales
- `oanda_client.py` — conexión con la API de OANDA
- `backtest.py` — backtesting con spread real y circuit breaker
- `live_bot.py` — trading automático en vivo

---

## ⚠️ Advertencias
- **Empezá siempre en demo.** Corré semanas en `practice` antes de pensar en real.
- **El backtest no garantiza el futuro.** Ni siquiera con spread incluido.
- **El riesgo es real.** El trading apalancado puede hacerte perder todo el capital.
- **Esto no es asesoramiento financiero.** Es una herramienta educativa.
- **No subas `config.py` a GitHub** con tus claves reales.