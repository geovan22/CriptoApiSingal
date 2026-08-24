# Crypto Signal Dashboard

Dashboard dinámico que monitorea BTC, ETH, SOL y BCH (editable), calcula
EMA 50/200, Bollinger Bands, MACD, RSI 14, Stoch RSI y PVT, y avisa cuando
detecta una señal de compra/venta con entrada, stop loss y take profit
sugeridos — replicando el marco de análisis que usamos manualmente en el chat.

**No necesita credenciales de Binance.** Usa el endpoint público de precios
(solo lectura de mercado), así que tu cuenta y tus fondos nunca están expuestos.

---

## Opción A (recomendada): correrlo gratis en la nube, verlo desde el celular

1. Crea una cuenta gratis en https://share.streamlit.io (Streamlit Community Cloud)
2. Sube esta carpeta a un repositorio de GitHub (puede ser privado)
3. En Streamlit Cloud, conecta el repo y selecciona `app.py` como archivo principal
4. Deploy. Te da una URL tipo `https://tuapp.streamlit.app`
5. Abre esa URL desde el navegador de tu teléfono y agrégala a tu pantalla de
   inicio (se ve y se siente como una app)

Ventaja: no gasta batería/datos de tu teléfono corriendo el proceso, y queda
disponible 24/7.

## Opción B: correrlo localmente en tu teléfono Android con Termux

1. Instala **Termux** desde F-Droid (no está en Play Store)
2. Dentro de Termux:
   ```
   pkg update && pkg install python
   pip install -r requirements.txt
   streamlit run app.py
   ```
3. Abre el navegador del teléfono en `http://localhost:8501`

Ventaja: todo corre local, sin depender de un tercero. Desventaja: tu
teléfono debe estar encendido con Termux corriendo para que siga vigilando.

## Opción C: correrlo en tu computadora y verlo desde el celular en la misma red WiFi

```
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```
Luego, desde el celular (misma WiFi), entra a `http://IP-DE-TU-PC:8501`

---

## Activar alertas push a tu Telegram (recomendado)

Un dashboard web no te avisa con la pantalla apagada. Para recibir
notificación push real:

1. En Telegram busca **@BotFather** → envía `/newbot` → sigue las instrucciones
2. Te da un **TOKEN** — cópialo
3. Busca tu bot recién creado y envíale cualquier mensaje (ej. "hola")
4. Abre en un navegador: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
5. Busca `"chat":{"id": ...}` en la respuesta — ese número es tu **CHAT_ID**
6. Pega ambos valores en `config.py`:
   ```python
   TELEGRAM_TOKEN = "tu_token_aqui"
   TELEGRAM_CHAT_ID = "tu_chat_id_aqui"
   ```

Con esto, cada vez que una señal cambie a COMPRA o VENTA, te llega un mensaje
al celular con precio, entrada, stop y take profit.

---

## Personalización

Edita `config.py`:
- `SYMBOLS`: lista de pares a vigilar (formato Binance, ej. `"ADAUSDT"`)
- `INTERVAL`: temporalidad (`"1h"`, `"4h"`, `"1d"`, etc.)
- `REFRESH_SECONDS`: cada cuánto se actualiza el dashboard

La lógica de señal (cuándo es COMPRA/VENTA/ESPERA) está en `signals.py`,
función `evaluate_signal()` — ahí puedes ajustar qué tan estricta o
permisiva es la confluencia de condiciones requerida.

---

## Importante

Esta herramienta es apoyo técnico automatizado, no asesoría financiera.
Las señales combinan indicadores derivados del precio (MACD, RSI, EMA, BB)
con PVT como aproximación al volumen. Como se discutió en el análisis manual,
esto **no reemplaza** datos reales de delta/order flow que tu guía de trading
profesional considera el estándar — es la mejor aproximación posible con
datos gratuitos y sin salir del ecosistema Python/Binance público.

Define siempre tu propio % de riesgo por operación antes de usar las
entradas/stops sugeridos.
