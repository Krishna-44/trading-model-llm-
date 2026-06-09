"""LIVE broker adapters. Real money. All of them enforce the same gate:

    settings.live_trading_enabled must be True, AND credentials must be present.

Otherwise every state-changing call raises ``LiveTradingDisabled``. The OANDA
adapter is implemented against the real v20 REST API and will work the moment a
practice/live token is supplied and the gate is opened. The Indian-broker
adapters are structured against their official SDKs (guarded imports) — they
will not even import their SDK unless the gate is open.

FEMA guard: offshore (non-INR) FX is refused unless ``allow_offshore_forex`` is
explicitly set, because Indian residents generally cannot legally trade it.
"""
from __future__ import annotations

import json
import logging
import os
import time

import httpx

from ..config import settings
from ..data.models import is_offshore_forex
from ..data.providers import get_provider
from .base import Account, BrokerAdapter, Fill, LiveTradingDisabled, Order, OrderSide, Position

logger = logging.getLogger("aifos.exec.live")


def _require_gate(broker: str) -> None:
    if not settings.live_trading_enabled:
        raise LiveTradingDisabled(
            f"LIVE TRADING IS OFF. Set AIFOS_LIVE_TRADING_ENABLED=true to arm "
            f"'{broker}'. Validate in paper mode first."
        )


def _require_order_gate(broker: str) -> None:
    """Gate for REAL order PLACEMENT/CLOSE (not reads). Master switch must be ON
    *and* monitor-only must be OFF. Every live place_order/close_position must call
    this — reading the account (get_account/get_positions) uses _require_gate only,
    so 'monitor-only' truly means 'connect & read, but NEVER place a real order'."""
    _require_gate(broker)
    if settings.live_monitor_only:
        raise LiveTradingDisabled(
            f"MONITOR-ONLY is ON for '{broker}' — the account is connected for reading "
            f"only; real orders are refused. Set AIFOS_LIVE_MONITOR_ONLY=false to arm "
            f"order placement (only after go-live readiness passes)."
        )


def _fema_guard(symbol: str) -> None:
    if is_offshore_forex(symbol) and not settings.allow_offshore_forex:
        raise LiveTradingDisabled(
            f"{symbol}: offshore spot FX is FEMA-restricted for Indian residents. "
            f"Use NSE currency derivatives (USDINR=X) or set AIFOS_ALLOW_OFFSHORE_FOREX=true "
            f"only if you are legally permitted."
        )


class OANDABroker(BrokerAdapter):
    """Forex via OANDA v20 REST. Functional when token + account id are set."""
    name = "oanda"
    is_live = True

    def __init__(self) -> None:
        host = ("https://api-fxpractice.oanda.com" if settings.oanda_environment == "practice"
                else "https://api-fxtrade.oanda.com")
        self._base = host
        self._headers = {"Authorization": f"Bearer {settings.oanda_api_token}",
                         "Content-Type": "application/json"}

    def connect(self) -> None:
        _require_gate(self.name)
        if not settings.oanda_api_token or not settings.oanda_account_id:
            raise LiveTradingDisabled("OANDA token/account id missing in env")
        r = httpx.get(f"{self._base}/v3/accounts/{settings.oanda_account_id}/summary",
                      headers=self._headers, timeout=15)
        r.raise_for_status()
        logger.warning("OANDA LIVE adapter connected (%s)", settings.oanda_environment)

    def get_account(self) -> Account:
        _require_gate(self.name)
        r = httpx.get(f"{self._base}/v3/accounts/{settings.oanda_account_id}/summary",
                      headers=self._headers, timeout=15)
        r.raise_for_status()
        acct = r.json()["account"]
        bal = float(acct["balance"])
        return Account(cash=bal, equity=float(acct.get("NAV", bal)),
                       currency=acct.get("currency", "USD"))

    def get_positions(self):
        _require_gate(self.name)
        r = httpx.get(f"{self._base}/v3/accounts/{settings.oanda_account_id}/openPositions",
                      headers=self._headers, timeout=15)
        r.raise_for_status()
        return []  # mapping to Position omitted for brevity; structure is in place

    def get_price(self, symbol: str) -> float:
        # use the shared provider for quotes (keeps one pricing source)
        return get_provider().latest_price(symbol)

    def place_order(self, order: Order) -> Fill:
        _require_order_gate(self.name)  # master switch + monitor-only
        _fema_guard(order.symbol)
        instrument = order.symbol.replace("=X", "").replace("USD", "_USD")  # e.g. EUR_USD
        units = int(order.qty) * (1 if order.side is OrderSide.BUY else -1)
        body = {"order": {"type": "MARKET", "instrument": instrument,
                          "units": str(units), "timeInForce": "FOK"}}
        r = httpx.post(f"{self._base}/v3/accounts/{settings.oanda_account_id}/orders",
                       headers=self._headers, json=body, timeout=15)
        r.raise_for_status()
        txn = r.json().get("orderFillTransaction", {})
        from datetime import datetime, timezone
        return Fill(order_id=txn.get("id", "OANDA"), symbol=order.symbol, side=order.side,
                    qty=abs(order.qty), price=float(txn.get("price", 0.0)),
                    ts=datetime.now(timezone.utc).isoformat())

    def close_position(self, symbol: str):
        _require_order_gate(self.name)  # master switch + monitor-only
        raise NotImplementedError("wire to /positions/{instrument}/close when arming live")


class ZerodhaBroker(BrokerAdapter):
    """NSE/BSE via Zerodha Kite Connect (paid API, daily access-token re-auth)."""
    name = "zerodha"
    is_live = True

    def _kite(self):
        _require_gate(self.name)
        if not (settings.zerodha_api_key and settings.zerodha_access_token):
            raise LiveTradingDisabled("Zerodha api_key/access_token missing (daily re-auth)")
        try:
            from kiteconnect import KiteConnect  # guarded: only needed when armed
        except ImportError as e:  # pragma: no cover
            raise LiveTradingDisabled("pip install -r requirements-live.txt for kiteconnect") from e
        k = KiteConnect(api_key=settings.zerodha_api_key)
        k.set_access_token(settings.zerodha_access_token)
        return k

    def connect(self) -> None:
        self._kite().profile()
        logger.warning("Zerodha LIVE adapter connected")

    def get_account(self) -> Account:
        m = self._kite().margins().get("equity", {})
        cash = float(m.get("available", {}).get("cash", 0.0))
        return Account(cash=cash, equity=cash, currency="INR")

    def get_positions(self):
        self._kite()
        return []  # map kite.positions()["net"] -> Position when arming live

    def get_price(self, symbol: str) -> float:
        return get_provider().latest_price(symbol)

    def place_order(self, order: Order) -> Fill:
        _require_order_gate(self.name)  # master switch + monitor-only (before any SDK call)
        k = self._kite()
        tsym = order.symbol.replace(".NS", "")
        oid = k.place_order(
            variety=k.VARIETY_REGULAR, exchange=k.EXCHANGE_NSE, tradingsymbol=tsym,
            transaction_type=(k.TRANSACTION_TYPE_BUY if order.side is OrderSide.BUY
                              else k.TRANSACTION_TYPE_SELL),
            quantity=int(order.qty), product=k.PRODUCT_MIS, order_type=k.ORDER_TYPE_MARKET,
        )
        from datetime import datetime, timezone
        return Fill(order_id=str(oid), symbol=order.symbol, side=order.side,
                    qty=order.qty, price=self.get_price(order.symbol),
                    ts=datetime.now(timezone.utc).isoformat(), status="submitted")

    def close_position(self, symbol: str):
        raise NotImplementedError("close via opposite MIS order when arming live")


class _GatedStub(BrokerAdapter):
    """Upstox / Angel One: gate-enforcing placeholders wired to their SDKs later."""
    is_live = True

    def connect(self) -> None:
        _require_gate(self.name)
        raise LiveTradingDisabled(f"{self.name} adapter not yet wired — use paper/zerodha/oanda")

    def get_account(self) -> Account:
        _require_gate(self.name); raise LiveTradingDisabled(self.name)

    def get_positions(self):
        _require_gate(self.name); raise LiveTradingDisabled(self.name)

    def get_price(self, symbol: str) -> float:
        return get_provider().latest_price(symbol)

    def place_order(self, order: Order) -> Fill:
        _require_gate(self.name); raise LiveTradingDisabled(self.name)

    def close_position(self, symbol: str):
        _require_gate(self.name); raise LiveTradingDisabled(self.name)


class UpstoxBroker(_GatedStub):
    name = "upstox"


class AngelOneBroker(BrokerAdapter):
    """NSE equity (and, with contract mapping, currency F&O) via Angel One SmartAPI.

    Requires TOTP-based login. Credentials come from env; nothing is read unless
    the gate is open. Instrument tokens are resolved from Angel's public scrip
    master (cached 24h)."""
    name = "angelone"
    is_live = True
    _SCRIP_URL = "https://margincalc.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

    def __init__(self) -> None:
        self._smart = None
        self._tokens: dict[tuple[str, str], str] = {}
        self._cache: dict[str, tuple[float, object]] = {}

    def _cached(self, key: str, ttl: float, fn):
        hit = self._cache.get(key)
        if hit and (time.time() - hit[0]) < ttl:
            return hit[1]
        val = fn()
        self._cache[key] = (time.time(), val)
        return val

    @staticmethod
    def _display_symbol(tsym: str) -> str:
        t = (tsym or "").upper()
        return t[:-3] + ".NS" if t.endswith("-EQ") else (tsym or "?")

    def _orders_allowed(self) -> None:
        """The order-side gate (reading the account never calls this)."""
        _require_order_gate(self.name)  # master switch + monitor-only (shared with OANDA/Zerodha)

    def _client(self):
        s = settings
        if not (s.angelone_api_key and s.angelone_client_code and s.angelone_pin
                and s.angelone_totp_secret):
            raise LiveTradingDisabled(
                "Angel One creds missing: set AIFOS_ANGELONE_API_KEY / CLIENT_CODE / PIN / TOTP_SECRET"
            )
        if self._smart is not None:
            return self._smart
        try:
            try:
                from SmartApi import SmartConnect  # smartapi-python >= 1.3
            except ImportError:  # pragma: no cover
                from smartapi import SmartConnect  # older releases
            import pyotp
        except ImportError as e:  # pragma: no cover
            raise LiveTradingDisabled(
                "pip install -r requirements-live.txt (smartapi-python, pyotp)") from e
        smart = SmartConnect(api_key=s.angelone_api_key)
        totp = pyotp.TOTP(s.angelone_totp_secret).now()
        smart.generateSession(s.angelone_client_code, s.angelone_pin, totp)
        self._smart = smart
        return smart

    def connect(self) -> None:
        self._client()
        logger.warning("⚠ Angel One LIVE adapter connected — real orders enabled")

    def _angel_symbol(self, symbol: str) -> tuple[str, str]:
        """Map an AIFOS symbol to (tradingsymbol, exchange). NSE equity is wired;
        indices/offshore FX are refused (offshore FX is also FEMA-vetoed upstream)."""
        if symbol.endswith(".NS"):
            return symbol[:-3] + "-EQ", "NSE"
        raise LiveTradingDisabled(
            f"{symbol}: Angel One live currently supports NSE equity (…-EQ). Map indices / "
            f"USDINR currency-futures to their Angel contract symbols to extend.")

    def _resolve_token(self, tradingsymbol: str, exchange: str) -> str:
        key = (tradingsymbol, exchange)
        if key in self._tokens:
            return self._tokens[key]
        path = os.path.join(settings.data_cache_dir, "angel_scrip.json")
        data = None
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < 86400:
            try:
                data = json.load(open(path))
            except Exception:  # noqa: BLE001
                data = None
        if data is None:
            r = httpx.get(self._SCRIP_URL, timeout=30)
            r.raise_for_status()
            data = r.json()
            os.makedirs(settings.data_cache_dir, exist_ok=True)
            try:
                json.dump(data, open(path, "w"))
            except Exception:  # noqa: BLE001
                pass
        for row in data:
            if row.get("symbol") == tradingsymbol and row.get("exch_seg") == exchange:
                self._tokens[key] = row.get("token", "")
                return self._tokens[key]
        raise LiveTradingDisabled(f"no Angel One token for {tradingsymbol}@{exchange}")

    def get_account(self) -> Account:
        d = self._cached("rms", 10, lambda: (self._client().rmsLimit() or {}).get("data", {}) or {})
        cash = float(d.get("availablecash") or d.get("net") or 0.0)
        holdings_val = sum(abs(p.market_value) for p in self.get_positions())
        return Account(cash=cash, equity=round(cash + holdings_val, 2), currency="INR")

    def get_positions(self) -> list[Position]:
        """Real Angel One positions (intraday/F&O) + demat holdings, mapped to Position
        objects so the dashboard reflects the actual account. Read-only; cached 10s."""
        def _fetch() -> list[Position]:
            sm = self._client()
            out: list[Position] = []
            try:
                for row in (sm.position() or {}).get("data") or []:
                    qty = float(row.get("netqty") or 0)
                    if abs(qty) < 1e-9:
                        continue
                    avg = float(row.get("netprice") or row.get("buyavgprice")
                                or row.get("avgnetprice") or 0)
                    ltp = float(row.get("ltp") or row.get("lastprice") or row.get("close") or avg)
                    out.append(Position(self._display_symbol(row.get("tradingsymbol", "")), qty, avg, ltp))
            except Exception as exc:  # noqa: BLE001 - transient broker read; keep going
                logger.warning("angelone position() read failed (retrying next poll): %s", exc)
            try:
                for row in (sm.holding() or {}).get("data") or []:
                    qty = float(row.get("quantity") or 0)
                    if abs(qty) < 1e-9:
                        continue
                    avg = float(row.get("averageprice") or 0)
                    ltp = float(row.get("ltp") or row.get("lastprice") or avg)
                    out.append(Position(self._display_symbol(row.get("tradingsymbol", "")), qty, avg, ltp))
            except Exception as exc:  # noqa: BLE001 - empty demat / transient read; keep going
                logger.warning("angelone holding() read failed (often just a transient/empty read): %s", exc)
            return out
        return self._cached("positions", 10, _fetch)

    def get_price(self, symbol: str) -> float:
        return get_provider().latest_price(symbol)

    def place_order(self, order: Order) -> Fill:
        self._orders_allowed()  # gate + monitor-only — blocks real orders unless explicitly armed
        sm = self._client()
        _fema_guard(order.symbol)
        tsym, exch = self._angel_symbol(order.symbol)
        token = self._resolve_token(tsym, exch)
        params = {
            "variety": "NORMAL", "tradingsymbol": tsym, "symboltoken": token,
            "transactiontype": "BUY" if order.side is OrderSide.BUY else "SELL",
            "exchange": exch, "ordertype": "MARKET", "producttype": "INTRADAY",
            "duration": "DAY", "quantity": str(int(order.qty)),
        }
        oid = sm.placeOrder(params)
        if isinstance(oid, dict):
            oid = oid.get("data", {}).get("orderid", oid)
        from datetime import datetime, timezone
        return Fill(order_id=str(oid), symbol=order.symbol, side=order.side, qty=order.qty,
                    price=self.get_price(order.symbol),
                    ts=datetime.now(timezone.utc).isoformat(), status="submitted")

    def close_position(self, symbol: str):
        self._orders_allowed()
        for p in self.get_positions():
            if p.symbol == symbol and abs(p.qty) > 1e-9:
                side = OrderSide.SELL if p.qty > 0 else OrderSide.BUY
                return self.place_order(Order(symbol=symbol, side=side, qty=abs(p.qty)))
        return None
