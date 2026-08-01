"""Currency mapping for EdgeLab news filtering (Phase 2, Module 2).

Given a trading symbol, determine which currencies' news events are relevant.
Gold/silver/crypto quote in USD, so their USD exposure is captured. Unknown
symbols fail SAFE (empty list => no news filtering) rather than guessing.
Only the standard library is used.
"""

from __future__ import annotations

import logging
import re

# Special quote/base tokens that are USD-correlated / priced-in-USD.
_NON_ISO_TOKENS = {"XAU": "XAU", "XAG": "XAG", "BTC": "BTC"}

_SUFFIX_RE = re.compile(r"(\.(i|raw|ecn|m|pro|std|demo)|[im])$", re.IGNORECASE)


def _strip_suffix(symbol: str) -> str:
    return _SUFFIX_RE.sub("", symbol).upper()


def get_currencies_for_symbol(symbol: str) -> list[str]:
    if not symbol or not symbol.strip():
        return []
    raw = _strip_suffix(symbol)
    if len(raw) == 3 and raw.isalpha():
        return [raw.upper()]
    if len(raw) != 6:
        _warn_unknown(symbol)
        return []
    base = raw[:3]
    quote = raw[-3:]
    if not (base.isalpha() and quote.isalpha()):
        _warn_unknown(symbol)
        return []
    # base is a special token (e.g. XAUUSD means gold priced in USD)
    if base in _NON_ISO_TOKENS:
        return ["USD", _NON_ISO_TOKENS[base]]
    quote_token = _NON_ISO_TOKENS.get(quote, quote)
    currencies = [base.upper(), quote_token.upper()]
    for c in currencies:
        if not (len(c) == 3 and c.isalpha() and c.isupper()):
            _warn_unknown(symbol)
            return []
    return currencies


def _warn_unknown(symbol: str) -> None:
    logging.getLogger("edgelab.news.currency_map").warning(
        "unknown symbol, no news filtering applied: %s", symbol
    )
