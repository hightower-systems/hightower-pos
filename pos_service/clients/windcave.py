import asyncio
import logging

import httpx
from fastapi import Depends
from lxml import etree
from pydantic import BaseModel, Field

from pos_service.config import Settings, get_settings

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30.0
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 0.5
SIGNATURE_TXN_STATUS_ID = "7"


class WindcaveClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_code: str | None = None,
        raw_xml: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_code = response_code
        self.raw_xml = raw_xml or ""


class WindcaveButton(BaseModel):
    name: str
    enabled: bool
    label: str = ""


class WindcaveDisplay(BaseModel):
    line_1: str = ""
    line_2: str = ""


class WindcaveResult(BaseModel):
    approved: bool = False
    auth_code: str | None = None
    card_brand: str | None = None
    card_masked: str | None = None
    card_last4: str | None = None
    dps_txn_ref: str | None = None
    txn_datetime: str | None = None
    response_code: str | None = None
    response_text: str | None = None
    amount_cents: int | None = None


class WindcaveStatusResponse(BaseModel):
    txn_ref: str
    txn_type: str = "Status"
    complete: bool = False
    status_id: str | None = None
    txn_status_id: str | None = None
    response_code: str | None = None
    timeout_seconds: int | None = None
    display: WindcaveDisplay = Field(default_factory=WindcaveDisplay)
    buttons: list[WindcaveButton] = Field(default_factory=list)
    receipt_text: str = ""
    receipt_width: int | None = None
    result: WindcaveResult | None = None
    raw_xml: str = ""

    @property
    def approved(self) -> bool:
        return self.complete and self.result is not None and self.result.approved

    @property
    def declined(self) -> bool:
        return self.complete and self.result is not None and not self.result.approved

    @property
    def signature_required(self) -> bool:
        return self.txn_status_id == SIGNATURE_TXN_STATUS_ID


class WindcaveClient:
    def __init__(
        self,
        *,
        base_url: str,
        user: str,
        key: str,
        station: str,
        vendor_id: str,
        pos_name: str,
        device_id: str,
        pos_version: str,
        currency: str,
        mock: bool = False,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        initial_backoff_s: float = INITIAL_BACKOFF_S,
    ) -> None:
        self._base_url = base_url
        self._user = user
        self._key = key
        self._station = station
        self._vendor_id = vendor_id
        self._pos_name = pos_name
        self._device_id = device_id
        self._pos_version = pos_version
        self._currency = currency
        self._mock = mock
        self._timeout_s = timeout_s
        self._initial_backoff_s = initial_backoff_s

    @classmethod
    def from_settings(cls, settings: Settings) -> "WindcaveClient":
        return cls(
            base_url=settings.windcave_base_url,
            user=settings.windcave_user,
            key=settings.windcave_key,
            station=settings.windcave_station,
            vendor_id=settings.windcave_vendor_id,
            pos_name=settings.windcave_pos_name,
            device_id=settings.windcave_device_id,
            pos_version=settings.windcave_pos_version,
            currency=settings.windcave_currency,
            mock=settings.windcave_mock,
        )

    @property
    def is_mock(self) -> bool:
        return self._mock

    async def charge(
        self,
        *,
        amount_cents: int,
        txn_ref: str,
        m_ref: str | None = None,
    ) -> WindcaveStatusResponse:
        if self._mock:
            return _mock_complete_response(txn_ref=txn_ref, amount_cents=amount_cents)
        body = self._build_transaction_xml(
            txn_type="Purchase",
            amount_cents=amount_cents,
            txn_ref=txn_ref,
            m_ref=m_ref,
        )
        return await self._post(body)

    async def refund(
        self,
        *,
        amount_cents: int,
        original_dps_txn_ref: str,
        txn_ref: str,
        m_ref: str | None = None,
    ) -> WindcaveStatusResponse:
        if self._mock:
            return _mock_complete_response(
                txn_ref=txn_ref,
                amount_cents=amount_cents,
                dps_txn_ref_override=f"MOCK-RF-{txn_ref[:12]}",
            )
        body = self._build_transaction_xml(
            txn_type="Refund",
            amount_cents=amount_cents,
            txn_ref=txn_ref,
            m_ref=m_ref,
            dps_txn_ref=original_dps_txn_ref,
        )
        return await self._post(body)

    async def status(self, *, txn_ref: str) -> WindcaveStatusResponse:
        if self._mock:
            return _mock_complete_response(txn_ref=txn_ref, amount_cents=0)
        scr = etree.Element("Scr", action="doScrHIT", user=self._user, key=self._key)
        etree.SubElement(scr, "Station").text = self._station
        etree.SubElement(scr, "TxnType").text = "Status"
        etree.SubElement(scr, "TxnRef").text = txn_ref
        return await self._post(_serialize(scr))

    async def cancel(self, *, txn_ref: str) -> bool:
        if self._mock:
            return True
        scr = etree.Element("Scr", action="doScrHIT", user=self._user, key=self._key)
        etree.SubElement(scr, "Station").text = self._station
        etree.SubElement(scr, "TxnType").text = "UI"
        etree.SubElement(scr, "UiType").text = "Bn"
        etree.SubElement(scr, "Name").text = "B2"
        etree.SubElement(scr, "Val").text = "CANCEL"
        etree.SubElement(scr, "TxnRef").text = txn_ref
        raw = await self._raw_post(_serialize(scr))
        root = _parse_xml(raw)
        success = (root.findtext("Success") or "").strip()
        return success == "1"

    def _build_transaction_xml(
        self,
        *,
        txn_type: str,
        amount_cents: int,
        txn_ref: str,
        m_ref: str | None = None,
        dps_txn_ref: str | None = None,
    ) -> bytes:
        scr = etree.Element("Scr", action="doScrHIT", user=self._user, key=self._key)
        etree.SubElement(scr, "Amount").text = _format_amount(amount_cents)
        etree.SubElement(scr, "Cur").text = self._currency
        etree.SubElement(scr, "TxnType").text = txn_type
        etree.SubElement(scr, "Station").text = self._station
        etree.SubElement(scr, "TxnRef").text = txn_ref
        if dps_txn_ref:
            etree.SubElement(scr, "DpsTxnRef").text = dps_txn_ref
        etree.SubElement(scr, "DeviceId").text = self._device_id
        etree.SubElement(scr, "PosName").text = self._pos_name
        if self._pos_version:
            etree.SubElement(scr, "PosVersion").text = self._pos_version
        etree.SubElement(scr, "VendorId").text = self._vendor_id
        if m_ref:
            etree.SubElement(scr, "MRef").text = m_ref
        return _serialize(scr)

    async def _post(self, xml_bytes: bytes) -> WindcaveStatusResponse:
        raw = await self._raw_post(xml_bytes)
        return _parse_status_response(raw)

    async def _raw_post(self, xml_bytes: bytes) -> str:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    r = await client.post(
                        self._base_url,
                        content=xml_bytes,
                        headers={"Content-Type": "text/xml; charset=utf-8"},
                    )
                if 500 <= r.status_code < 600:
                    last_exc = WindcaveClientError(
                        f"windcave returned {r.status_code}",
                        status_code=r.status_code,
                        raw_xml=r.text,
                    )
                    await self._backoff(attempt)
                    continue
                if r.status_code >= 400:
                    raise WindcaveClientError(
                        f"windcave returned {r.status_code}",
                        status_code=r.status_code,
                        raw_xml=r.text,
                    )
                return r.text
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                last_exc = exc
                await self._backoff(attempt)
                continue
        assert last_exc is not None
        if isinstance(last_exc, WindcaveClientError):
            raise last_exc
        raise WindcaveClientError(
            f"windcave request failed after {MAX_RETRIES} attempts: {last_exc!r}"
        ) from last_exc

    async def _backoff(self, attempt: int) -> None:
        if self._initial_backoff_s <= 0:
            return
        await asyncio.sleep(self._initial_backoff_s * (2**attempt))


def _format_amount(amount_cents: int) -> str:
    if amount_cents < 0:
        raise ValueError("amount must be non-negative")
    return f"{amount_cents / 100:.2f}"


def _serialize(scr: "etree._Element") -> bytes:
    return etree.tostring(scr, encoding="utf-8")


def _parse_xml(raw: str) -> "etree._Element":
    try:
        return etree.fromstring(raw.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise WindcaveClientError(f"invalid xml from windcave: {exc}", raw_xml=raw) from exc


def _parse_status_response(raw: str) -> WindcaveStatusResponse:
    root = _parse_xml(raw)
    txn_ref = (root.findtext("TxnRef") or "").strip()
    txn_type = (root.findtext("TxnType") or "Status").strip()
    complete = (root.findtext("Complete") or "0").strip() == "1"
    status_id = (root.findtext("StatusId") or "").strip() or None
    txn_status_id = (root.findtext("TxnStatusId") or "").strip() or None
    response_code = (root.findtext("ReCo") or "").strip() or None
    tmo_text = (root.findtext("Tmo") or "").strip()
    timeout_seconds = int(tmo_text) if tmo_text.isdigit() else None

    display = WindcaveDisplay(
        line_1=(root.findtext("DL1") or "").strip(),
        line_2=(root.findtext("DL2") or "").strip(),
    )

    buttons: list[WindcaveButton] = []
    for name in ("B1", "B2"):
        elem = root.find(name)
        if elem is None:
            continue
        en = elem.get("en", "0")
        label = (elem.text or "").strip()
        buttons.append(WindcaveButton(name=name, enabled=en == "1", label=label))

    receipt_text = (root.findtext("Rcpt") or "").strip()
    rcpt_w_text = (root.findtext("RcptW") or "").strip()
    receipt_width = int(rcpt_w_text) if rcpt_w_text.isdigit() else None

    result: WindcaveResult | None = None
    result_elem = root.find("Result")
    if result_elem is not None:
        ap = (result_elem.findtext("AP") or "0").strip()
        cn = (result_elem.findtext("CN") or "").strip() or None
        amt_a_text = (result_elem.findtext("AmtA") or "").strip()
        amount_cents = int(amt_a_text) if amt_a_text.isdigit() else None
        result = WindcaveResult(
            approved=ap == "1",
            auth_code=(result_elem.findtext("AC") or "").strip() or None,
            card_brand=(result_elem.findtext("CT") or "").strip() or None,
            card_masked=cn,
            card_last4=cn[-4:] if cn else None,
            dps_txn_ref=(result_elem.findtext("TR") or "").strip() or None,
            txn_datetime=(result_elem.findtext("DT") or "").strip() or None,
            response_code=(result_elem.findtext("RC") or "").strip() or None,
            response_text=(result_elem.findtext("RT") or "").strip() or None,
            amount_cents=amount_cents,
        )

    return WindcaveStatusResponse(
        txn_ref=txn_ref,
        txn_type=txn_type,
        complete=complete,
        status_id=status_id,
        txn_status_id=txn_status_id,
        response_code=response_code,
        timeout_seconds=timeout_seconds,
        display=display,
        buttons=buttons,
        receipt_text=receipt_text,
        receipt_width=receipt_width,
        result=result,
        raw_xml=raw,
    )


def _mock_complete_response(
    *, txn_ref: str, amount_cents: int, dps_txn_ref_override: str | None = None
) -> WindcaveStatusResponse:
    dps_txn_ref = dps_txn_ref_override or f"MOCK-TR-{txn_ref[:12]}"
    return WindcaveStatusResponse(
        txn_ref=txn_ref,
        txn_type="Status",
        complete=True,
        status_id="6",
        txn_status_id="8",
        response_code="00",
        timeout_seconds=20,
        display=WindcaveDisplay(line_1="APPROVED"),
        buttons=[
            WindcaveButton(name="B1", enabled=False),
            WindcaveButton(name="B2", enabled=False),
        ],
        receipt_text=(
            f"        AvidMax (mock)\n"
            f"AUTHORISATION 000000\n"
            f"AMOUNT  ${amount_cents / 100:.2f}\n"
            f"APPROVED\n"
        ),
        receipt_width=30,
        result=WindcaveResult(
            approved=True,
            auth_code="000000",
            card_brand="Visa",
            card_masked="411111******1111",
            card_last4="1111",
            dps_txn_ref=dps_txn_ref,
            txn_datetime="20260508140000",
            response_code="00",
            response_text="",
            amount_cents=amount_cents,
        ),
        raw_xml="<!-- mock -->",
    )


def get_windcave_client(settings: Settings = Depends(get_settings)) -> WindcaveClient:
    return WindcaveClient.from_settings(settings)
