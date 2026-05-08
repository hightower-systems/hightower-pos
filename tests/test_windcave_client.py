import httpx
import pytest
import respx
from lxml import etree

from pos_service.clients.windcave import (
    WindcaveClient,
    WindcaveClientError,
    WindcaveStatusResponse,
    _format_amount,
)

WINDCAVE_URL = "https://demo.windcave.com/SandboxPxHIT.aspx"


def _client(*, mock: bool = False) -> WindcaveClient:
    return WindcaveClient(
        base_url=WINDCAVE_URL,
        user="AvidMax",
        key="test-key",
        station="TEST-STATION",
        vendor_id="Hightower",
        pos_name="AvidMaxPOS",
        device_id="AvidMax-Reg1",
        pos_version="1.0.0",
        currency="USD",
        mock=mock,
        timeout_s=2.0,
        initial_backoff_s=0.0,
    )


INITIAL_RESPONSE_XML = """<Scr>
  <TxnType>Status</TxnType>
  <StatusId>3</StatusId>
  <TxnStatusId>2</TxnStatusId>
  <Complete>0</Complete>
  <ReCo/>
  <Tmo>20</Tmo>
  <TxnRef>abc-123</TxnRef>
  <DL1>PRESENT/INSERT</DL1>
  <DL2>SWIPE CARD</DL2>
  <B1 en="0"/>
  <B2 en="1">CANCEL</B2>
</Scr>"""


FINAL_APPROVED_XML = """<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>abc-123</TxnRef>
  <StatusId>6</StatusId>
  <TxnStatusId>8</TxnStatusId>
  <Complete>1</Complete>
  <RcptW>30</RcptW>
  <Rcpt>          *----------EFTPOS----------*27 Mar 18 13:13       CHEQUESWIPE VISA          CARD 411111******1111AUTHORISATION         000289REFERENCE             029013PURCHASE          NZD1.00TOTAL             NZD1.00                 APPROVED                          PIN VERIFIED                  *----------------*       CUSTOMER COPY                          PLEASE RETAIN          FOR YOUR RECORDS</Rcpt>
  <Result>
    <AC>000289</AC>
    <AP>1</AP>
    <CN>411111******1111</CN>
    <CT>Visa</CT>
    <CH>VISA TEST CARD/</CH>
    <DT>20180327131306</DT>
    <DT_TZ>NZT</DT_TZ>
    <DS>20180327180000</DS>
    <DS_TZ>NZT</DS_TZ>
    <PIX></PIX>
    <RID></RID>
    <RRN></RRN>
    <ST>788359</ST>
    <TR>0000000100e1a6f9</TR>
    <DBID>0000010001128730</DBID>
    <RC>00</RC>
    <RT></RT>
    <RTT>4050</RTT>
    <AmtA>100</AmtA>
  </Result>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>APPROVED</DL1>
  <DL2></DL2>
  <B1 en="0"></B1>
  <B2 en="0"></B2>
</Scr>"""


FINAL_DECLINED_XML = """<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>abc-456</TxnRef>
  <StatusId>6</StatusId>
  <TxnStatusId>8</TxnStatusId>
  <Complete>1</Complete>
  <Result>
    <AC></AC>
    <AP>0</AP>
    <CN>411111******2222</CN>
    <CT>Visa</CT>
    <DT>20260508140000</DT>
    <RC>05</RC>
    <RT>DO NOT HONOUR</RT>
    <AmtA>5398</AmtA>
    <TR>0000000200000001</TR>
  </Result>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>DECLINED</DL1>
  <DL2></DL2>
  <B1 en="0"></B1>
  <B2 en="0"></B2>
</Scr>"""


SIGNATURE_XML = """<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>abc-789</TxnRef>
  <StatusId>4</StatusId>
  <TxnStatusId>7</TxnStatusId>
  <Complete>0</Complete>
  <RcptW>30</RcptW>
  <Rcpt>signature receipt content</Rcpt>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>SIGNATURE OK?</DL1>
  <DL2>YES/NO</DL2>
  <B1 en="1">YES</B1>
  <B2 en="1">NO</B2>
</Scr>"""


CANCEL_RESPONSE_XML = """<Scr>
  <TxnType>UI</TxnType>
  <TxnRef>abc-123</TxnRef>
  <Success>1</Success>
  <RC></RC>
</Scr>"""


def _request_root(route: respx.Route) -> etree._Element:
    body = route.calls.last.request.content
    return etree.fromstring(body)


@respx.mock
async def test_charge_sends_purchase_xml() -> None:
    route = respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=INITIAL_RESPONSE_XML)
    )
    response = await _client().charge(amount_cents=4990, txn_ref="abc-123", m_ref="cart#1")
    assert route.called
    root = _request_root(route)
    assert root.tag == "Scr"
    assert root.get("action") == "doScrHIT"
    assert root.get("user") == "AvidMax"
    assert root.get("key") == "test-key"
    assert root.findtext("Amount") == "49.90"
    assert root.findtext("Cur") == "USD"
    assert root.findtext("TxnType") == "Purchase"
    assert root.findtext("Station") == "TEST-STATION"
    assert root.findtext("TxnRef") == "abc-123"
    assert root.findtext("DeviceId") == "AvidMax-Reg1"
    assert root.findtext("PosName") == "AvidMaxPOS"
    assert root.findtext("PosVersion") == "1.0.0"
    assert root.findtext("VendorId") == "Hightower"
    assert root.findtext("MRef") == "cart#1"
    assert root.find("DpsTxnRef") is None
    assert isinstance(response, WindcaveStatusResponse)


@respx.mock
async def test_charge_initial_response_parsed() -> None:
    respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=INITIAL_RESPONSE_XML)
    )
    r = await _client().charge(amount_cents=4990, txn_ref="abc-123")
    assert r.complete is False
    assert r.txn_ref == "abc-123"
    assert r.status_id == "3"
    assert r.txn_status_id == "2"
    assert r.timeout_seconds == 20
    assert r.display.line_1 == "PRESENT/INSERT"
    assert r.display.line_2 == "SWIPE CARD"
    b2 = next(b for b in r.buttons if b.name == "B2")
    assert b2.enabled is True
    assert b2.label == "CANCEL"
    assert r.result is None
    assert r.signature_required is False


def test_format_amount_d_cc() -> None:
    assert _format_amount(0) == "0.00"
    assert _format_amount(1) == "0.01"
    assert _format_amount(105) == "1.05"
    assert _format_amount(4990) == "49.90"
    assert _format_amount(199900) == "1999.00"
    with pytest.raises(ValueError):
        _format_amount(-1)


@respx.mock
async def test_refund_includes_dps_txn_ref() -> None:
    route = respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=INITIAL_RESPONSE_XML)
    )
    await _client().refund(
        amount_cents=5398,
        original_dps_txn_ref="0000000100e1a6f9",
        txn_ref="rf-987",
    )
    root = _request_root(route)
    assert root.findtext("TxnType") == "Refund"
    assert root.findtext("Amount") == "53.98"
    assert root.findtext("TxnRef") == "rf-987"
    assert root.findtext("DpsTxnRef") == "0000000100e1a6f9"


@respx.mock
async def test_status_request_minimal_xml() -> None:
    route = respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=FINAL_APPROVED_XML)
    )
    await _client().status(txn_ref="abc-123")
    root = _request_root(route)
    assert root.findtext("TxnType") == "Status"
    assert root.findtext("Station") == "TEST-STATION"
    assert root.findtext("TxnRef") == "abc-123"
    assert root.find("Amount") is None
    assert root.find("DeviceId") is None


@respx.mock
async def test_status_complete_approved_response_parsed() -> None:
    respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=FINAL_APPROVED_XML)
    )
    r = await _client().status(txn_ref="abc-123")
    assert r.complete is True
    assert r.approved is True
    assert r.declined is False
    assert r.signature_required is False
    assert r.result is not None
    assert r.result.approved is True
    assert r.result.auth_code == "000289"
    assert r.result.card_brand == "Visa"
    assert r.result.card_masked == "411111******1111"
    assert r.result.card_last4 == "1111"
    assert r.result.dps_txn_ref == "0000000100e1a6f9"
    assert r.result.txn_datetime == "20180327131306"
    assert r.result.response_code == "00"
    assert r.result.amount_cents == 100
    assert r.receipt_width == 30
    assert "EFTPOS" in r.receipt_text
    assert r.display.line_1 == "APPROVED"


@respx.mock
async def test_status_declined_response_parsed() -> None:
    respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=FINAL_DECLINED_XML)
    )
    r = await _client().status(txn_ref="abc-456")
    assert r.complete is True
    assert r.approved is False
    assert r.declined is True
    assert r.result is not None
    assert r.result.approved is False
    assert r.result.response_code == "05"
    assert r.result.response_text == "DO NOT HONOUR"
    assert r.result.amount_cents == 5398


@respx.mock
async def test_status_signature_stage_flagged() -> None:
    respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=SIGNATURE_XML)
    )
    r = await _client().status(txn_ref="abc-789")
    assert r.complete is False
    assert r.signature_required is True
    assert r.txn_status_id == "7"
    yes = next(b for b in r.buttons if b.name == "B1")
    no = next(b for b in r.buttons if b.name == "B2")
    assert yes.enabled is True and yes.label == "YES"
    assert no.enabled is True and no.label == "NO"


@respx.mock
async def test_cancel_sends_button_xml_and_returns_true() -> None:
    route = respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(200, content=CANCEL_RESPONSE_XML)
    )
    ok = await _client().cancel(txn_ref="abc-123")
    assert ok is True
    root = _request_root(route)
    assert root.findtext("TxnType") == "UI"
    assert root.findtext("UiType") == "Bn"
    assert root.findtext("Name") == "B2"
    assert root.findtext("Val") == "CANCEL"
    assert root.findtext("TxnRef") == "abc-123"


@respx.mock
async def test_cancel_returns_false_when_success_zero() -> None:
    respx.post(WINDCAVE_URL).mock(
        return_value=httpx.Response(
            200,
            content="<Scr><TxnType>UI</TxnType><TxnRef>abc-123</TxnRef><Success>0</Success><RC>XX</RC></Scr>",
        )
    )
    ok = await _client().cancel(txn_ref="abc-123")
    assert ok is False


@respx.mock
async def test_retries_5xx_then_succeeds() -> None:
    route = respx.post(WINDCAVE_URL).mock(
        side_effect=[
            httpx.Response(503, text=""),
            httpx.Response(503, text=""),
            httpx.Response(200, content=FINAL_APPROVED_XML),
        ]
    )
    r = await _client().status(txn_ref="abc-123")
    assert route.call_count == 3
    assert r.complete is True


@respx.mock
async def test_retries_exhausted_raises() -> None:
    respx.post(WINDCAVE_URL).mock(return_value=httpx.Response(503, text=""))
    with pytest.raises(WindcaveClientError) as exc:
        await _client().status(txn_ref="abc-123")
    assert exc.value.status_code == 503


@respx.mock
async def test_does_not_retry_4xx() -> None:
    route = respx.post(WINDCAVE_URL).mock(return_value=httpx.Response(400, text=""))
    with pytest.raises(WindcaveClientError) as exc:
        await _client().status(txn_ref="abc-123")
    assert exc.value.status_code == 400
    assert route.call_count == 1


@respx.mock
async def test_invalid_xml_raises() -> None:
    respx.post(WINDCAVE_URL).mock(return_value=httpx.Response(200, content="not xml at all"))
    with pytest.raises(WindcaveClientError):
        await _client().status(txn_ref="abc-123")


async def test_mock_charge_returns_complete_approved() -> None:
    r = await _client(mock=True).charge(amount_cents=4990, txn_ref="abc-123")
    assert r.complete is True
    assert r.approved is True
    assert r.result is not None
    assert r.result.amount_cents == 4990
    assert r.result.dps_txn_ref is not None
    assert r.result.dps_txn_ref.startswith("MOCK-TR-")


async def test_mock_refund_returns_complete_approved_with_distinct_dps_txn_ref() -> None:
    r = await _client(mock=True).refund(
        amount_cents=4990,
        original_dps_txn_ref="0000000100e1a6f9",
        txn_ref="rf-987",
    )
    assert r.complete is True
    assert r.approved is True
    assert r.result is not None
    assert r.result.dps_txn_ref is not None
    assert r.result.dps_txn_ref.startswith("MOCK-RF-")


async def test_mock_status_returns_complete() -> None:
    r = await _client(mock=True).status(txn_ref="abc-123")
    assert r.complete is True


async def test_mock_cancel_returns_true() -> None:
    ok = await _client(mock=True).cancel(txn_ref="abc-123")
    assert ok is True
