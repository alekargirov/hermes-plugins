"""Tool schemas — what the model reads when deciding to call these tools."""

CRYPTO_PRICE = {
    "name": "crypto_price",
    "description": (
        "Get the CURRENT market price of one or more cryptocurrencies, with 24h "
        "and 7d change, 24h high/low and volume. Use this whenever the user asks "
        "what a coin is worth, whether it is up or down, or mentions a crypto "
        "price at all — your training data is stale, this is live. "
        "Accepts ticker symbols (BTC, ETH, SOL, XMR, ...) and any fiat quote "
        "currency (USD, EUR, GBP, ...). Data comes from Kraken, falling back to "
        "Hyperliquid, Binance, Coinbase and CoinGecko, so it works without any "
        "API key."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ticker symbols to quote, e.g. ['BTC'] or ['BTC','ETH','SOL'].",
            },
            "currency": {
                "type": "string",
                "description": "Fiat quote currency. Default USD.",
            },
            "provider": {
                "type": "string",
                "enum": ["kraken", "hyperliquid", "binance", "coinbase", "coingecko"],
                "description": (
                    "Force a specific source. Omit unless the user asked for one — "
                    "the default chain already falls back on failure."
                ),
            },
        },
        "required": ["symbols"],
    },
}

CRYPTO_HISTORY = {
    "name": "crypto_history",
    "description": (
        "Get historical price data (OHLC candles) for one cryptocurrency over a "
        "period, plus summary stats: open, close, change %, high, low. Use this "
        "for questions about how a coin has performed over days/weeks/months, "
        "for trend or volatility questions, or when the user wants a chart's "
        "worth of numbers. For 'what is it worth right now', use crypto_price."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'BTC'."},
            "currency": {"type": "string", "description": "Fiat quote currency. Default USD."},
            "days": {
                "type": "integer",
                "description": "How many days back to cover (1-365). Default 7.",
            },
            "max_points": {
                "type": "integer",
                "description": "Cap on returned candles (default 60). Keeps output readable.",
            },
        },
        "required": ["symbol"],
    },
}

CRYPTO_ALERT = {
    "name": "crypto_alert",
    "description": (
        "Manage crypto price alerts for the user: create, list, delete, enable, "
        "disable, or check them now. Alerts are evaluated by a scheduled job and "
        "delivered to the user's chat, so use this when the user says things like "
        "'tell me when BTC hits 80k', 'let me know if ETH drops below 2000', or "
        "'ping me if anything moves more than 5% today'. Alert kinds: 'above' and "
        "'below' (absolute price), 'pct_move' (absolute change over a 24h or 7d "
        "window), 'pct_from' (moved N% from the price at the moment the alert was "
        "created). Use action 'list' to answer 'what alerts do I have'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "delete", "enable", "disable", "check"],
                "description": "What to do. 'check' evaluates all alerts against live prices right now.",
            },
            "symbol": {"type": "string", "description": "Ticker symbol — required for 'create'."},
            "kind": {
                "type": "string",
                "enum": ["above", "below", "pct_move", "pct_from"],
                "description": "Alert type — required for 'create'.",
            },
            "threshold": {
                "type": "number",
                "description": (
                    "Price for 'above'/'below'; percentage (e.g. 5 for 5%) for "
                    "'pct_move'/'pct_from'."
                ),
            },
            "currency": {"type": "string", "description": "Fiat quote currency. Default USD."},
            "window": {
                "type": "string",
                "enum": ["24h", "7d"],
                "description": "Lookback window for 'pct_move'. Default 24h.",
            },
            "repeat": {
                "type": "string",
                "enum": ["once", "always"],
                "description": (
                    "'once' fires a single time then disables itself (default). "
                    "'always' re-arms after the cooldown."
                ),
            },
            "cooldown_minutes": {
                "type": "integer",
                "description": "For repeat='always', minimum gap between firings. Default 60.",
            },
            "note": {
                "type": "string",
                "description": "Short reminder of why the user set this alert.",
            },
            "alert_id": {
                "type": "string",
                "description": "Alert id — required for 'delete', 'enable', 'disable'.",
            },
        },
        "required": ["action"],
    },
}
