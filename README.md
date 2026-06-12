# Bot de Trading Forex — Mean Reversion (Bollinger Bands)

Bot de trading algorítmico en Python que se conecta a OANDA. Hace backtesting con
datos históricos reales y opera automáticamente en cuenta demo (o real, bajo tu responsabilidad).

**Estrategia:** Mean Reversion con Bandas de Bollinger + filtro RSI + stop-loss dinámico por ATR.

---

## 1. Requisitos

- Python 3.9 o superior
- Una cuenta demo de OANDA (gratis)

## 2. Conseguir credenciales de OANDA (gratis)

1. Andá a https://www.oanda.com/ y creá una cuenta **Practice / Demo** (dinero virtual).
2. Una vez dentro, buscá **"Manage API Access"** y generá un **token** (API key).
3. Anotá tu **Account ID** (tiene formato `101-001-XXXXXXX-001`).

## 3. Instalación

```bash
# Descomprimí el proyecto y entrá a la carpeta
cd forex-bot

# Instalá la única dependencia
pip install -r requirements.txt
```

## 4. Configuración

Abrí `config.py` y pegá tus credenciales:

```python
OANDA_API_TOKEN  = "tu_token_aca"
OANDA_ACCOUNT_ID = "101-001-XXXXXXX-001"
OANDA_ENV        = "practice"   # dejalo en practice para demo
```

Ahí mismo podés ajustar el par (`INSTRUMENT`), el timeframe (`GRANULARITY`),
el riesgo por operación (`RISK_PER_TRADE`) y los parámetros de la estrategia.

## 5. Correr el backtest (recomendado primero)

```bash
python backtest.py
```

Baja datos históricos reales de OANDA y te muestra: retorno total, retorno mensual
estimado, Sharpe ratio, win rate, drawdown máximo y la lista de operaciones.
**No ejecuta ninguna orden real.**

## 6. Correr el bot en vivo (demo)

```bash
python live_bot.py
```

Con `OANDA_ENV = "practice"` opera con dinero virtual. El bot revisa el mercado cada
5 minutos, abre y cierra posiciones solo, y manda el stop-loss/take-profit junto con
cada orden (así tus posiciones quedan protegidas aunque el bot se apague).

Para frenarlo: `Ctrl + C`.

---

## Cómo funciona la estrategia

| Acción | Condición |
|---|---|
| **Comprar (LONG)** | El precio toca o baja de la banda inferior **y** el RSI < 45 (sobreventa) |
| **Vender (SHORT)** | El precio toca o supera la banda superior **y** el RSI > 55 (sobrecompra) |
| **Cerrar** | El precio vuelve a la media móvil (objetivo), toca el stop-loss, o el take-profit |

El tamaño de cada posición se calcula para arriesgar exactamente el % que configuraste
(por defecto 1%), usando el ATR para medir la volatilidad actual.

## Archivos del proyecto

- `config.py` — tus credenciales y todos los parámetros ajustables
- `strategy.py` — indicadores (Bollinger, ATR, RSI) y lógica de señales
- `oanda_client.py` — conexión con la API de OANDA
- `backtest.py` — backtesting con datos históricos reales
- `live_bot.py` — trading automático en vivo

---

## ⚠️ Advertencias importantes

- **Empezá siempre en demo.** Corré el bot semanas en `practice` antes de pensar en dinero real.
- **El backtest no garantiza el futuro.** Que haya funcionado en el pasado no significa que funcione mañana.
- **El riesgo es real.** El trading con apalancamiento puede hacerte perder todo tu capital.
- **Esto no es asesoramiento financiero.** Es una herramienta educativa. Vos sos responsable de tus decisiones.
- **No subas `config.py` a GitHub** con tus claves reales. Agregalo a `.gitignore`.
