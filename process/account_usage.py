import json
import math
from dataclasses import dataclass

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from signaling.debug_signal import debug_error


SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"


@dataclass(frozen=True)
class AccountUsage:
    subscription_anlas: int
    purchased_anlas: int
    regular_percent: float | None
    purchased_percent: float | None
    unavailable_reason: str = ""

    @property
    def total_anlas(self) -> int:
        return self.subscription_anlas + self.purchased_anlas

    @property
    def total_percent(self) -> float | None:
        if self.regular_percent is None or self.purchased_percent is None:
            return None
        return self.regular_percent + self.purchased_percent


def parse_account_usage(payload: object) -> AccountUsage:
    if not isinstance(payload, dict):
        raise ValueError("Invalid subscription response: expected an object.")
    balances = payload.get("trainingStepsLeft")
    if not isinstance(balances, dict):
        raise ValueError("Subscription response has no Anlas balances.")

    def balance(name: str) -> int:
        value = balances.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Invalid subscription balance: {name}.")
        return value

    subscription = balance("fixedTrainingStepsLeft")
    purchased = balance("purchasedTrainingSteps")
    active = payload.get("active")
    if not isinstance(active, bool):
        raise ValueError("Subscription response has no valid active status.")
    usage = payload.get("usage")
    if not active:
        return AccountUsage(subscription, purchased, None, None, "Subscription is inactive.")
    if usage is None:
        return AccountUsage(subscription, purchased, None, None, "V5 allowance is not provided for this account.")
    if not isinstance(usage, dict) or not isinstance(usage.get("isNegative"), bool):
        raise ValueError("Invalid V5 usage status.")
    if usage["isNegative"]:
        return AccountUsage(subscription, purchased, None, None, "V5 allowance is unavailable.")

    def percent(name: str) -> float:
        value = usage.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Invalid V5 usage percentage: {name}.")
        try:
            value = float(value)
        except OverflowError:
            raise ValueError(f"Invalid V5 usage percentage: {name}.") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid V5 usage percentage: {name}.")
        return value

    regular = percent("percent")
    extra = percent("purchasedPercent")
    if not math.isfinite(regular + extra):
        raise ValueError("Invalid combined V5 usage percentage.")
    return AccountUsage(subscription, purchased, regular, extra)


class AccountUsageController(QObject):
    updated = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self._key = ""
        self._reply: QNetworkReply | None = None
        self._pending = False
        self._closed = False
        self._revision = 0
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(600)
        self._debounce.timeout.connect(self.refresh)

    def set_api_key(self, key: str) -> None:
        key = key.strip()
        if self._closed or key == self._key:
            return
        self._key = key
        self._revision += 1
        self._pending = False
        self._debounce.stop()
        old_reply = self._reply
        self._reply = None
        if old_reply is not None:
            old_reply.abort()
        self.updated.emit("key_changed" if key else "no_key", None)
        if key:
            self._debounce.start()

    def refresh(self) -> None:
        if self._closed:
            return
        if not self._key:
            self.updated.emit("no_key", None)
            return
        if self._debounce.isActive():
            return
        if self._reply is not None:
            self._pending = True
            return
        request = QNetworkRequest(QUrl(SUBSCRIPTION_URL))
        request.setRawHeader(QByteArray(b"Authorization"), QByteArray(f"Bearer {self._key}".encode()))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        request.setTransferTimeout(15_000)
        self.updated.emit("loading", None)
        reply = self.network.get(request)
        self._reply = reply
        deadline = QTimer(reply)
        deadline.setSingleShot(True)
        deadline.timeout.connect(reply.abort)
        reply.finished.connect(deadline.stop)
        deadline.start(15_000)
        revision = self._revision
        reply.finished.connect(lambda: self._finished(reply, revision))

    def _finished(self, reply: QNetworkReply, revision: int) -> None:
        if self._closed or revision != self._revision or reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = ""
        snapshot = None
        if status in (401, 403):
            error = "Account usage authentication failed. Check your API key."
        elif reply.error() != QNetworkReply.NetworkError.NoError:
            error = "Account usage request failed or timed out. Check your connection."
        elif status != 200:
            error = f"Account usage request returned HTTP {status}."
        else:
            raw = bytes(reply.readAll())
            if len(raw) > 1_000_000:
                error = "Account usage response exceeded the allowed size."
            else:
                try:
                    snapshot = parse_account_usage(json.loads(raw))
                except (ValueError, UnicodeDecodeError) as exception:
                    # JSON decoder errors may contain response text; never log it.
                    error = (
                        "Account usage response is not valid JSON."
                        if isinstance(exception, (json.JSONDecodeError, UnicodeDecodeError))
                        else str(exception)
                    )
        reply.deleteLater()
        if error:
            debug_error("Account Usage", error)
            self.updated.emit("error", error)
        else:
            self.updated.emit("ready", snapshot)
        if self._pending:
            self._pending = False
            QTimer.singleShot(0, self.refresh)

    def close(self) -> None:
        self._closed = True
        self._revision += 1
        self._debounce.stop()
        self._pending = False
        reply = self._reply
        self._reply = None
        if reply is not None:
            reply.abort()
