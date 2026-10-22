"""Conservative create-record validation; all schema and values are fabricated."""

import copy
import math

import pytest

from feishu_bitable_mcp.config import BitableError
from feishu_bitable_mcp.server import validate_bind
from feishu_bitable_mcp.writes import validate_fields

SCHEMA = [
    {"field_name": "Title", "type": 1},
    {"field_name": "Phone", "type": 13},
    {"field_name": "Amount", "type": 2},
    {"field_name": "Done", "type": 7},
    {"field_name": "When", "type": 5},
    {
        "field_name": "Stage",
        "type": 3,
        "property": {"options": [{"name": "New"}, {"name": "Ready"}]},
    },
    {"field_name": "Tags", "type": 4, "property": {"options": [{"name": "Red"}, {"name": "Blue"}]}},
    {"field_name": "Website", "type": 15},
]


@pytest.mark.parametrize("name", ["Title", "Phone"])
def test_text_and_phone_accept_only_bounded_strings(name):
    assert validate_fields({name: ""}, SCHEMA) == {name: ""}
    assert validate_fields({name: "synthetic example"}, SCHEMA) == {name: "synthetic example"}
    assert validate_fields({name: "x" * 5000}, SCHEMA) == {name: "x" * 5000}
    for value in [123, True, None, ["text"], {"text": "nested"}, "x" * 5001]:
        with pytest.raises(BitableError):
            validate_fields({name: value}, SCHEMA)


@pytest.mark.parametrize("value", [0, -42, 1.25])
def test_numbers_accept_finite_numeric_values(value):
    assert validate_fields({"Amount": value}, SCHEMA) == {"Amount": value}


@pytest.mark.parametrize("value", [True, False, "12", None, math.nan, math.inf, -math.inf, 10**400])
def test_numbers_reject_boolean_nonfinite_and_out_of_range_values(value):
    with pytest.raises(BitableError):
        validate_fields({"Amount": value}, SCHEMA)


@pytest.mark.parametrize("value", [True, False])
def test_checkbox_accepts_boolean(value):
    assert validate_fields({"Done": value}, SCHEMA) == {"Done": value}


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_checkbox_rejects_non_boolean(value):
    with pytest.raises(BitableError):
        validate_fields({"Done": value}, SCHEMA)


@pytest.mark.parametrize("value", [0, 1_700_000_000_000, 253_402_300_799_999])
def test_date_accepts_bounded_unix_milliseconds(value):
    assert validate_fields({"When": value}, SCHEMA) == {"When": value}


@pytest.mark.parametrize("value", [True, 1.5, "1700000000000", -1, 253_402_300_800_000, None])
def test_date_rejects_other_types_and_out_of_range_values(value):
    with pytest.raises(BitableError):
        validate_fields({"When": value}, SCHEMA)


def test_static_select_values_are_preserved_without_new_options():
    assert validate_fields({"Stage": "Ready", "Tags": ["Red", "Blue"]}, SCHEMA) == {
        "Stage": "Ready",
        "Tags": ["Red", "Blue"],
    }
    assert validate_fields({"Tags": []}, SCHEMA) == {"Tags": []}


@pytest.mark.parametrize(
    "fields",
    [
        {"Stage": "Unconfigured"},
        {"Stage": ["New"]},
        {"Stage": None},
        {"Tags": ["Red", "Unconfigured"]},
        {"Tags": ["Red", "Red"]},
        {"Tags": "Red"},
        {"Tags": [1]},
        {"Tags": ["Red"] * 101},
    ],
)
def test_select_rejects_new_options_duplicate_choices_and_wrong_types(fields):
    with pytest.raises(BitableError):
        validate_fields(fields, SCHEMA)


@pytest.mark.parametrize("url", ["https://example.test/path", "http://example.test:8080/path?q=1"])
def test_hyperlinks_require_exact_text_link_structure(url):
    value = {"text": "Example", "link": url}
    assert validate_fields({"Website": value}, SCHEMA) == {"Website": value}


@pytest.mark.parametrize(
    "value",
    [
        "https://example.test",
        {"link": "https://example.test"},
        {"text": "Example", "link": "https://example.test", "extra": "unexpected"},
        {"text": 3, "link": "https://example.test"},
        {"text": "Example", "link": "javascript:alert(1)"},
        {"text": "Example", "link": "file:///tmp/synthetic"},
        {"text": "Example", "link": "https://"},
        {"text": "Example", "link": "https://user:password@example.test"},
        {"text": "Example", "link": "https://example.test/path\nheader"},
        {"text": "Example", "link": "https://example.test:notaport/path"},
        {"text": "Example", "link": "https://example.test:99999/path"},
        {"text": "Example", "link": "https://example.test\\other"},
    ],
)
def test_hyperlinks_reject_malformed_or_unsafe_values(value):
    with pytest.raises(BitableError):
        validate_fields({"Website": value}, SCHEMA)


@pytest.mark.parametrize("kind", [11, 17, 18, 19, 20, 21, 1001, 1002, 1003, 1004, 1005])
def test_computed_person_link_attachment_and_system_fields_fail_closed(kind):
    with pytest.raises(BitableError, match="unsupported|read-only"):
        validate_fields({"Restricted": "synthetic"}, [{"field_name": "Restricted", "type": kind}])


@pytest.mark.parametrize("fields", [{"Unknown": "value"}, {1: "value"}])
def test_unknown_and_non_string_field_names_are_rejected(fields):
    with pytest.raises(BitableError, match="Unknown field"):
        validate_fields(fields, SCHEMA)


@pytest.mark.parametrize("fields", [{}, [], None, {f"Synthetic-{i}": "value" for i in range(101)}])
def test_empty_non_dict_and_excessive_field_counts_are_rejected(fields):
    with pytest.raises(BitableError, match="between 1 and 100"):
        validate_fields(fields, SCHEMA)


def test_payload_size_uses_utf8_bytes_and_is_bounded_before_api_call():
    schema = [{"field_name": f"Text-{i}", "type": 1} for i in range(10)]
    # Each string is within the per-field length limit; UTF-8 payload exceeds 50 kB.
    values = {f"Text-{i}": "字" * 2000 for i in range(10)}
    with pytest.raises(BitableError, match="50000 bytes"):
        validate_fields(values, schema)


@pytest.mark.parametrize("value", [set(), b"bytes", complex(1, 2), object()])
def test_non_json_values_fail_with_clear_error(value):
    with pytest.raises(BitableError, match="JSON-serializable"):
        validate_fields({"Title": value}, SCHEMA)


def test_validation_preserves_inputs_and_raw_schema():
    values = {
        "Title": "Synthetic",
        "Tags": ["Red"],
        "Website": {"text": "Example", "link": "https://example.test"},
    }
    original_values = copy.deepcopy(values)
    original_schema = copy.deepcopy(SCHEMA)
    assert validate_fields(values, SCHEMA) == original_values
    assert values == original_values
    assert SCHEMA == original_schema


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.0.0.2", "::1"])
def test_loopback_http_can_run_without_bearer_auth(host):
    validate_bind(host, "")


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "example.test"])
def test_remote_http_binding_requires_auth(host):
    with pytest.raises(BitableError, match="MCP_AUTH_TOKEN"):
        validate_bind(host, "")
    validate_bind(host, "synthetic-secret-with-at-least-32-characters")
