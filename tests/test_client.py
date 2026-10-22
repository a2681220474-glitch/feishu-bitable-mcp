"""Feishu behavior tested with synthetic responses and HTTPX MockTransport only."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from feishu_bitable_mcp import client as client_module
from feishu_bitable_mcp.client import TOKEN_ROUTE, FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings, Target

TARGET = Target("DemoBaseToken0001", "tblDemoTable01", "vewDemoView1")
APP_SECRET = "synthetic-application-secret"
AUTH_TOKEN = "synthetic-auth-token-000000000000000000"
TENANT_TOKEN = "synthetic-tenant-token-0001"
RECORDS_ROUTE = FeishuClient.table_route(TARGET, "/records")


def success(data):
    return httpx.Response(200, json={"code": 0, "data": data})


def token_response(token=TENANT_TOKEN, expiry=7200):
    return httpx.Response(200, json={"code": 0, "tenant_access_token": token, "expire": expiry})


@pytest.fixture
def settings():
    return Settings("synthetic-app-id", APP_SECRET, auth_token=AUTH_TOKEN)


@pytest.fixture
async def mock_client(settings):
    clients = []

    def factory(handler, *, policy=None):
        requests = []

        async def dispatch(request):
            requests.append(request)
            response = handler(request)
            return await response if hasattr(response, "__await__") else response

        client = FeishuClient(policy or settings, transport=httpx.MockTransport(dispatch))
        clients.append(client)
        return client, requests

    yield factory
    for client in clients:
        await client.close()


def is_token(request):
    return request.url.path.endswith(TOKEN_ROUTE)


async def test_concurrent_first_requests_share_one_token_request(mock_client):
    arrived = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        assert is_token(request)
        calls += 1
        arrived.set()
        await release.wait()
        return token_response()

    client, requests = mock_client(handler)
    pending = [asyncio.create_task(client.token()) for _ in range(12)]
    await arrived.wait()
    release.set()
    assert await asyncio.gather(*pending) == [TENANT_TOKEN] * 12
    assert calls == len(requests) == 1
    assert json.loads(requests[0].content) == {
        "app_id": "synthetic-app-id",
        "app_secret": APP_SECRET,
    }


@pytest.mark.parametrize("expiry,refresh_after", [(7200, 7080), (10, 9)])
async def test_token_refreshes_before_real_expiry(mock_client, monkeypatch, expiry, refresh_after):
    clock = [100.0]
    monkeypatch.setattr(client_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    client, requests = mock_client(lambda request: token_response(expiry=expiry))
    await client.token()
    clock[0] += refresh_after - 0.1
    await client.token()
    assert len(requests) == 1
    clock[0] += 0.2
    await client.token()
    assert len(requests) == 2


@pytest.mark.parametrize("always_expired", [False, True])
async def test_expired_read_token_refreshes_and_retries_only_once(mock_client, always_expired):
    tokens = 0
    reads = 0

    def handler(request):
        nonlocal tokens, reads
        if is_token(request):
            tokens += 1
            return token_response(token=f"synthetic-token-{tokens}")
        reads += 1
        assert request.headers["authorization"] == f"Bearer synthetic-token-{tokens}"
        if reads == 1 or always_expired:
            return httpx.Response(200, json={"code": 99991668, "msg": "Expired"})
        return success({"result": "read"})

    client, _ = mock_client(handler)
    if always_expired:
        with pytest.raises(BitableError, match="99991668"):
            await client.request("GET", RECORDS_ROUTE)
    else:
        assert await client.request("GET", RECORDS_ROUTE) == {"result": "read"}
    assert tokens == reads == 2


@pytest.mark.parametrize("status,code", [(429, 99991400), (503, 1), (200, 99991668)])
async def test_record_creation_is_never_retried(mock_client, status, code):
    policy = Settings(
        "synthetic-app-id",
        APP_SECRET,
        auth_token=AUTH_TOKEN,
        enable_writes=True,
        write_tables=frozenset({TARGET.key}),
    )

    def handler(request):
        if is_token(request):
            return token_response()
        assert request.method == "POST"
        return httpx.Response(status, json={"code": code, "msg": "Synthetic write error"})

    client, requests = mock_client(handler, policy=policy)
    with pytest.raises(BitableError, match=f"code={code}"):
        await client.create(TARGET, {"Name": "Synthetic example"})
    assert sum(not is_token(request) for request in requests) == 1
    assert sum(is_token(request) for request in requests) == 1


@pytest.mark.parametrize("body", ["not-json", [], {"code": 0, "data": []}])
async def test_malformed_write_result_warns_outcome_unknown(mock_client, body):
    policy = Settings(
        "synthetic-app-id",
        APP_SECRET,
        auth_token=AUTH_TOKEN,
        enable_writes=True,
        write_tables=frozenset({TARGET.key}),
    )

    def handler(request):
        if is_token(request):
            return token_response()
        if isinstance(body, str):
            return httpx.Response(200, text=body)
        return httpx.Response(200, json=body)

    client, requests = mock_client(handler, policy=policy)
    with pytest.raises(BitableError, match="outcome is unknown"):
        await client.create(TARGET, {"Title": "Fictional example"})
    assert sum(not is_token(request) for request in requests) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_read_failures_retry_at_most_three_times(mock_client, status):
    def handler(request):
        if is_token(request):
            return token_response()
        return httpx.Response(
            status, headers={"Retry-After": "0"}, json={"code": 1, "msg": "Temporary"}
        )

    client, requests = mock_client(handler)
    with pytest.raises(BitableError, match=f"HTTP {status}"):
        await client.request("GET", RECORDS_ROUTE)
    assert sum(not is_token(request) for request in requests) == 3


async def test_transient_read_can_recover_without_changing_request(mock_client):
    reads = 0

    def handler(request):
        nonlocal reads
        if is_token(request):
            return token_response()
        reads += 1
        if reads < 3:
            return httpx.Response(
                503, headers={"Retry-After": "0"}, json={"code": 1, "msg": "Temporary"}
            )
        return success({"items": []})

    client, requests = mock_client(handler)
    assert await client.request("GET", RECORDS_ROUTE, params={"page_size": 100}) == {"items": []}
    read_requests = [request for request in requests if not is_token(request)]
    assert len(read_requests) == 3
    assert len({str(request.url) for request in read_requests}) == 1


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_failures_do_not_leak_details_or_duplicate_writes(
    mock_client,
    method,
    exception,
):
    def handler(request):
        if is_token(request):
            return token_response()
        raise exception(f"Synthetic failure with {APP_SECRET}", request=request)

    client, requests = mock_client(handler)
    with pytest.raises(BitableError) as error:
        await client.request(method, RECORDS_ROUTE)
    assert APP_SECRET not in str(error.value)
    assert ("Write outcome is unknown" in str(error.value)) == (method == "POST")
    assert sum(not is_token(request) for request in requests) == 1


@pytest.mark.parametrize("body", [b"not json", b"[]", b"null"])
async def test_invalid_upstream_body_is_safe(mock_client, body):
    def handler(request):
        return token_response() if is_token(request) else httpx.Response(502, content=body)

    client, _ = mock_client(handler)
    with pytest.raises(BitableError, match="HTTP 502; invalid"):
        await client.request("GET", RECORDS_ROUTE)


async def test_http_failure_is_not_success_even_when_api_code_is_zero(mock_client):
    def handler(request):
        return (
            token_response()
            if is_token(request)
            else httpx.Response(403, json={"code": 0, "msg": "Permission denied", "data": {}})
        )

    client, requests = mock_client(handler)
    with pytest.raises(BitableError, match="HTTP 403; code=0; msg=Permission denied"):
        await client.request("GET", RECORDS_ROUTE)
    assert len(requests) == 2


async def test_error_messages_redact_secrets_and_preserve_useful_code(mock_client):
    user_token = "synthetic-user-token-001"
    refresh_token = "synthetic-refresh-token-001"
    unexpected_bearer = "synthetic-other-bearer-001"
    message = (
        f"app_secret={APP_SECRET}, tenant_access_token={TENANT_TOKEN}, "
        f"user_access_token='{user_token}', refresh_token=\"{refresh_token}\", "
        f"Bearer {unexpected_bearer} {AUTH_TOKEN}\nSynthetic failure"
    )

    def handler(request):
        return (
            token_response()
            if is_token(request)
            else httpx.Response(403, json={"code": 1254302, "msg": message})
        )

    client, _ = mock_client(handler)
    with pytest.raises(BitableError) as error:
        await client.request("GET", RECORDS_ROUTE)
    rendered = str(error.value)
    assert "1254302" in rendered
    assert "Synthetic failure" in rendered
    assert "\n" not in rendered
    for secret in [
        APP_SECRET,
        TENANT_TOKEN,
        user_token,
        refresh_token,
        unexpected_bearer,
        AUTH_TOKEN,
    ]:
        assert secret not in rendered


@pytest.mark.parametrize("expiry", [0, -1, True, "7200", None])
async def test_invalid_auth_response_expiry_is_not_cached(mock_client, expiry):
    client, _ = mock_client(lambda request: token_response(expiry=expiry))
    with pytest.raises(BitableError, match="positive expiry"):
        await client.token()


async def test_fields_include_full_unknown_and_formula_configuration(mock_client):
    raw = {
        "field_id": "fldDemoFormula1",
        "field_name": "Computed example",
        "type": 20,
        "is_primary": False,
        "description": "Synthetic schema",
        "property": {"formula_expression": "1+2", "formatter": "0.00"},
        "future_metadata": {"preserve": [1, 2, 3]},
    }

    def handler(request):
        if is_token(request):
            return token_response()
        return success({"items": [raw], "has_more": False})

    client, _ = mock_client(handler)
    fields = await client.fields(TARGET)
    assert fields == [{**raw, "field_type_name": "Formula"}]
    assert raw.get("field_type_name") is None


async def test_all_fields_traverse_every_page_in_order(mock_client):
    def handler(request):
        if is_token(request):
            return token_response()
        cursor = request.url.params.get("page_token")
        assert request.url.params["page_size"] == "100"
        if cursor is None:
            return success(
                {
                    "items": [{"field_id": "fldDemoText1", "type": 1}],
                    "has_more": True,
                    "page_token": "page-2",
                }
            )
        assert cursor == "page-2"
        return success({"items": [{"field_id": "fldDemoNumber1", "type": 2}], "has_more": False})

    client, requests = mock_client(handler)
    assert [field["field_id"] for field in await client.fields(TARGET)] == [
        "fldDemoText1",
        "fldDemoNumber1",
    ]
    assert len(requests) == 3


@pytest.mark.parametrize("next_token", [None, "", "synthetic-repeated-cursor"])
async def test_field_pagination_missing_or_repeated_token_fails(mock_client, next_token):
    def handler(request):
        if is_token(request):
            return token_response()
        return success({"items": [], "has_more": True, "page_token": next_token})

    client, requests = mock_client(handler)
    with pytest.raises(BitableError, match="pagination did not advance"):
        await client.fields(TARGET)
    assert sum(not is_token(request) for request in requests) <= 2


async def test_records_forward_view_and_page_and_preserve_raw_record_metadata(mock_client):
    raw = {
        "record_id": "recDemoRecord01",
        "fields": {
            "Name": [{"text": "Synthetic example", "type": "text"}],
            "Unknown future field": {"structured": [1, False, None]},
        },
        "created_time": 123456789,
        "future_metadata": {"keep": True},
    }

    def handler(request):
        if is_token(request):
            return token_response()
        assert request.url.params == httpx.QueryParams(
            {
                "page_size": 17,
                "page_token": "page-1",
                "view_id": TARGET.view_id,
            }
        )
        return success(
            {
                "items": [raw],
                "has_more": True,
                "page_token": "page-2",
                "total": 31,
                "future_page_metadata": "keep",
            }
        )

    client, _ = mock_client(handler)
    page = await client.records(TARGET, 17, "page-1")
    assert page["records"] == [raw]
    assert page["total"] == 31
    assert page["future_page_metadata"] == "keep"
    assert page["has_more"] is True
    assert page["page_token"] == "page-2"


@pytest.mark.parametrize("next_token", [None, "", "page-1"])
async def test_records_reject_nonadvancing_pagination(mock_client, next_token):
    def handler(request):
        return (
            token_response()
            if is_token(request)
            else success(
                {
                    "items": [],
                    "has_more": True,
                    "page_token": next_token,
                }
            )
        )

    client, _ = mock_client(handler)
    with pytest.raises(BitableError, match="pagination did not advance"):
        await client.records(TARGET, 10, "page-1")


async def test_info_resolves_exact_table_id_across_pages(mock_client):
    def handler(request):
        if is_token(request):
            return token_response()
        if not request.url.path.endswith("/tables"):
            return success({"app": {"name": "Synthetic Base"}})
        if request.url.params.get("page_token") is None:
            return success(
                {
                    "items": [{"table_id": "tblOtherDemo01", "name": "Same synthetic name"}],
                    "has_more": True,
                    "page_token": "synthetic-next-page",
                }
            )
        return success(
            {
                "items": [{"table_id": TARGET.table_id, "name": "Same synthetic name"}],
                "has_more": False,
            }
        )

    client, _ = mock_client(handler)
    result = await client.info(TARGET)
    assert result["table"]["table_id"] == TARGET.table_id
    assert result["view_id"] == TARGET.view_id
    assert result["base"]["name"] == "Synthetic Base"


async def test_same_named_table_cannot_substitute_for_requested_id(mock_client):
    def handler(request):
        if is_token(request):
            return token_response()
        if request.url.path.endswith("/tables"):
            return success(
                {
                    "items": [{"table_id": "tblOtherDemo01", "name": "Synthetic table"}],
                    "has_more": False,
                }
            )
        return success({"app": {"name": "Synthetic Base"}})

    client, _ = mock_client(handler)
    with pytest.raises(BitableError, match="exact URL"):
        await client.info(TARGET)


@pytest.mark.parametrize("operation", ["info", "fields", "records", "create"])
async def test_authorization_rejects_before_token_or_data_request(mock_client, operation):
    policy = Settings(
        "synthetic-app-id",
        APP_SECRET,
        read_tables=frozenset({("OtherDemoBase0001", "tblOtherDemo01")}),
    )

    def handler(request):
        pytest.fail("Denied requests must never reach even the mock HTTP transport")

    client, requests = mock_client(handler, policy=policy)
    with pytest.raises(BitableError, match="FEISHU_READ_TABLE_URLS"):
        if operation == "records":
            await client.records(TARGET, 10)
        elif operation == "create":
            await client.create(TARGET, {"Name": "Synthetic example"})
        else:
            await getattr(client, operation)(TARGET)
    assert requests == []
