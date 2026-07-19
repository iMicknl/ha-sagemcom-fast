"""Collect a privacy-safe capability profile from a Sagemcom router."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from getpass import getpass
import json
import os
from pathlib import Path
import re
import statistics
import sys
from time import perf_counter
from typing import Final

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import AccessRestrictionException, UnknownPathException

PROFILE_SCHEMA_VERSION: Final = 1

METRIC_XPATHS: Final[Mapping[str, str]] = {
    "uptime": "Device/DeviceInfo/UpTime",
    "wan_status": "Device/IP/Interfaces/Interface[Alias='IP_DATA']/Status",
    "dsl_downstream_rate": ("Device/DSL/Channels/Channel[@uid='1']/DownstreamCurrRate"),
    "dsl_upstream_rate": ("Device/DSL/Channels/Channel[@uid='1']/UpstreamCurrRate"),
}

SCHEMA_XPATHS: Final[Mapping[str, str]] = {
    "ip": "Device/IP",
    "ip_interfaces": "Device/IP/Interfaces",
    "ip_interface": "Device/IP/Interfaces/Interface",
    "wan_stats": "Device/IP/Interfaces/Interface[Alias='IP_DATA']/Stats",
    "dsl": "Device/DSL",
    "dsl_channels": "Device/DSL/Channels",
    "dsl_channel": "Device/DSL/Channels/Channel",
    "docsis": "Device/Docsis",
    "docsis_cable_modem": "Device/Docsis/CableModem",
    "docsis_downstreams": "Device/Docsis/CableModem/Downstreams",
    "docsis_downstream": "Device/Docsis/CableModem/Downstreams/Downstream",
    "docsis_upstreams": "Device/Docsis/CableModem/Upstreams",
    "docsis_upstream": "Device/Docsis/CableModem/Upstreams/Upstream",
    "cable_modem": "Device/CableModem",
    "cable_modem_downstreams": "Device/CableModem/Downstreams",
    "cable_modem_downstream": "Device/CableModem/Downstreams/Downstream",
    "cable_modem_upstreams": "Device/CableModem/Upstreams",
    "cable_modem_upstream": "Device/CableModem/Upstreams/Upstream",
}

DOCSIS_COLLECTIONS: Final[Mapping[str, tuple[str, str]]] = {
    "downstream": (
        "Device/Docsis/CableModem/Downstreams",
        "Downstream",
    ),
    "upstream": (
        "Device/Docsis/CableModem/Upstreams",
        "Upstream",
    ),
}

CONNECTED_WAN_STATUSES: Final = frozenset({"connected", "online", "up"})
DISCONNECTED_WAN_STATUSES: Final = frozenset(
    {
        "disconnected",
        "dormant",
        "down",
        "error",
        "lowerlayerdown",
        "notpresent",
        "offline",
    }
)
DSL_RATE_UNAVAILABLE: Final = 2**32 - 1

MAC_ADDRESS_PATTERN: Final = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
)
IPV4_ADDRESS_PATTERN: Final = re.compile(
    r"(?<!\d)(?:25[0-5]|2[0-4]\d|1?\d?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?!\d)"
)
IPV6_ADDRESS_PATTERN: Final = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{0,4}:){2,}[0-9a-f]{0,4}(?![0-9a-f])"
)
SAFE_ERROR_DESCRIPTION_PATTERN: Final = re.compile(r"[A-Z][A-Z0-9_ -]{0,79}")
SAFE_FIELD_PATTERN: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,79}")


class UnavailableMetric(ValueError):
    """A readable metric currently reports a defined unavailable sentinel."""


def _safe_error(exception: Exception) -> dict[str, int | str]:
    """Return allowlisted protocol error metadata without arbitrary messages."""
    details: dict[str, int | str] = {"exception": type(exception).__name__}
    payload = exception.args[0] if exception.args else None
    if not isinstance(payload, Mapping):
        return details

    code = payload.get("code")
    description = payload.get("description")
    if isinstance(code, int) and not isinstance(code, bool):
        details["code"] = code
    if isinstance(description, str) and SAFE_ERROR_DESCRIPTION_PATTERN.fullmatch(
        description
    ):
        details["description"] = description
    return details


def _safe_label(value: object) -> str | None:
    """Return short gateway metadata unless it resembles an address."""
    if not isinstance(value, str) or not (normalized := value.strip()):
        return None
    if len(normalized) > 160 or any(
        pattern.search(normalized)
        for pattern in (
            MAC_ADDRESS_PATTERN,
            IPV4_ADDRESS_PATTERN,
            IPV6_ADDRESS_PATTERN,
        )
    ):
        return "<redacted>"
    if any(character in normalized for character in "\r\n\t"):
        return "<redacted>"
    return normalized


def _safe_field_name(value: object) -> str | None:
    """Return an API schema field name, never an identifier-like mapping key."""
    if not isinstance(value, str) or not SAFE_FIELD_PATTERN.fullmatch(value):
        return None
    if any(
        pattern.fullmatch(value)
        for pattern in (
            MAC_ADDRESS_PATTERN,
            IPV4_ADDRESS_PATTERN,
            IPV6_ADDRESS_PATTERN,
        )
    ):
        return None
    return value


def _field_types(value: object) -> dict[str, str]:
    """Describe safe mapping field names without retaining their values."""
    if not isinstance(value, Mapping):
        return {}

    fields: dict[str, str] = {}
    for field, field_value in value.items():
        if safe_field := _safe_field_name(field):
            fields[safe_field] = type(field_value).__name__
    return dict(sorted(fields.items()))


def _value_shape(value: object) -> dict[str, object]:
    """Summarize a response shape without copying keys used as identifiers."""
    if isinstance(value, list):
        item = next((candidate for candidate in value if candidate is not None), None)
        result: dict[str, object] = {
            "type": "list",
            "count": len(value),
            "item_type": type(item).__name__ if item is not None else "-",
        }
        if isinstance(item, Mapping):
            result["item_fields"] = _field_types(item)
            result["locked_count"] = sum(
                candidate.get("lock_status") is True
                for candidate in value
                if isinstance(candidate, Mapping)
            )
        return result

    if not isinstance(value, Mapping):
        return {"type": type(value).__name__}

    nested_items = [item for item in value.values() if isinstance(item, Mapping)]
    if nested_items and len(nested_items) == len(value):
        return {
            "type": "keyed_dict",
            "count": len(value),
            "item_type": "dict",
            "item_fields": _field_types(nested_items[0]),
        }

    result = {"type": "dict", "fields": _field_types(value)}
    if len(value) == 1:
        result["wrapped_value"] = _value_shape(next(iter(value.values())))
    return result


def _normalize_metric(name: str, value: object) -> object:
    """Validate a capability value without returning it to the profile."""
    if name == "wan_status":
        if not isinstance(value, str) or not (normalized := value.strip()):
            raise ValueError("invalid WAN status")
        return normalized

    if isinstance(value, bool):
        raise ValueError("invalid numeric value")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exception:
        raise ValueError("invalid numeric value") from exception
    if normalized < 0:
        raise ValueError("invalid numeric value")
    if name.startswith("dsl_") and normalized == DSL_RATE_UNAVAILABLE:
        raise UnavailableMetric
    return normalized


def _wan_connected(value: object) -> bool | None:
    """Map known WAN states without retaining the raw provider string."""
    if not isinstance(value, str):
        return None
    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    if normalized in CONNECTED_WAN_STATUSES:
        return True
    if normalized in DISCONNECTED_WAN_STATUSES:
        return False
    return None


async def _probe_metrics(
    client: SagemcomClient,
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """Probe scalar capabilities while discarding every raw value."""
    results: dict[str, dict[str, object]] = {}
    benchmark_paths: dict[str, str] = {}

    for name, xpath in METRIC_XPATHS.items():
        try:
            value = await client.get_value_by_xpath(xpath)
        except AccessRestrictionException:
            result: dict[str, object] = {"status": "blocked"}
        except UnknownPathException:
            result = {"status": "missing"}
        except Exception as exception:  # pylint: disable=broad-except
            result = {"status": "error", "error": _safe_error(exception)}
        else:
            try:
                normalized = _normalize_metric(name, value)
            except UnavailableMetric:
                result = {
                    "status": "supported",
                    "available": False,
                    "value_type": type(value).__name__,
                }
            except ValueError:
                result = {
                    "status": "malformed",
                    "value_type": type(value).__name__,
                }
            else:
                result = {
                    "status": "supported",
                    "available": True,
                    "value_type": type(normalized).__name__,
                }
                benchmark_paths[name] = xpath
                if name == "wan_status":
                    result["connected"] = _wan_connected(normalized)
        results[name] = result

    return results, benchmark_paths


async def _benchmark_reads(
    client: SagemcomClient,
    xpaths: Mapping[str, str],
    runs: int,
) -> dict[str, object]:
    """Compare confirmed scalar reads without retaining any response values."""
    if len(xpaths) < 2:
        return {"status": "skipped", "confirmed_action_count": len(xpaths)}

    sequential_timings: list[float] = []
    batch_timings: list[float] = []
    decoded_values = 0
    try:
        for _ in range(runs):
            started = perf_counter()
            for name, xpath in xpaths.items():
                _normalize_metric(name, await client.get_value_by_xpath(xpath))
            sequential_timings.append((perf_counter() - started) * 1000)

            started = perf_counter()
            values = await client.get_values_by_xpaths(dict(xpaths))
            batch_timings.append((perf_counter() - started) * 1000)
            decoded_values = sum(
                1
                for name, value in values.items()
                if name in xpaths and _metric_is_valid(name, value)
            )
    except Exception as exception:  # pylint: disable=broad-except
        return {
            "status": "error",
            "confirmed_action_count": len(xpaths),
            "error": _safe_error(exception),
        }

    sequential_ms = statistics.median(sequential_timings)
    batch_ms = statistics.median(batch_timings)
    return {
        "status": "ok",
        "runs": runs,
        "confirmed_action_count": len(xpaths),
        "decoded_value_count": decoded_values,
        "sequential_median_ms": round(sequential_ms, 1),
        "batch_median_ms": round(batch_ms, 1),
        "speedup": round(sequential_ms / batch_ms, 2) if batch_ms else 0,
    }


def _metric_is_valid(name: str, value: object) -> bool:
    """Return whether one benchmark value validates without exposing it."""
    try:
        _normalize_metric(name, value)
    except ValueError:
        return False
    return True


async def _probe_schemas(client: SagemcomClient) -> dict[str, dict[str, object]]:
    """Probe fixed candidate hierarchies and retain only response shapes."""
    results: dict[str, dict[str, object]] = {}
    for name, xpath in SCHEMA_XPATHS.items():
        try:
            value = await client.get_value_by_xpath(xpath)
        except AccessRestrictionException:
            result: dict[str, object] = {"status": "blocked", "path": xpath}
        except UnknownPathException:
            result = {"status": "missing", "path": xpath}
        except Exception as exception:  # pylint: disable=broad-except
            result = {
                "status": "error",
                "path": xpath,
                "error": _safe_error(exception),
            }
        else:
            result = {
                "status": "supported",
                "path": xpath,
                "shape": _value_shape(value),
            }
        results[name] = result
    return results


async def _probe_indexed_docsis(
    client: SagemcomClient,
) -> dict[str, dict[str, object]]:
    """Test actual collection UIDs internally without including them in output."""
    results: dict[str, dict[str, object]] = {}
    for channel_type, (collection_xpath, object_name) in DOCSIS_COLLECTIONS.items():
        template = f"{collection_xpath}/{object_name}[@uid='<collection uid>']"
        try:
            collection = await client.get_value_by_xpath(collection_xpath)
            if not isinstance(collection, list):
                raise ValueError("collection is not a list")
            channel = next(
                (
                    item
                    for item in collection
                    if isinstance(item, Mapping)
                    and isinstance(item.get("uid"), int)
                    and not isinstance(item.get("uid"), bool)
                ),
                None,
            )
            if channel is None:
                raise ValueError("collection has no numeric UID")
            indexed_xpath = f"{collection_xpath}/{object_name}[@uid='{channel['uid']}']"
            value = await client.get_value_by_xpath(indexed_xpath)
        except AccessRestrictionException:
            result: dict[str, object] = {
                "status": "blocked",
                "path_template": template,
            }
        except UnknownPathException:
            result = {"status": "missing", "path_template": template}
        except ValueError as exception:
            result = {
                "status": "malformed",
                "path_template": template,
                "reason": type(exception).__name__,
            }
        except Exception as exception:  # pylint: disable=broad-except
            result = {
                "status": "error",
                "path_template": template,
                "error": _safe_error(exception),
            }
        else:
            result = {
                "status": "supported",
                "path_template": template,
                "shape": _value_shape(value),
            }
        results[channel_type] = result
    return results


def _gateway_metadata(gateway: object, client: SagemcomClient) -> dict[str, str | None]:
    """Select firmware fields and remove embedded connection identifiers."""
    sensitive_values = {
        normalized.casefold()
        for value in (
            getattr(gateway, "serial_number", None),
            getattr(gateway, "mac_address", None),
            getattr(client, "host", None),
            getattr(client, "username", None),
            getattr(client, "password", None),
        )
        if isinstance(value, str) and (normalized := value.strip())
    }
    metadata: dict[str, str | None] = {}
    for field in (
        "manufacturer",
        "model_name",
        "model_number",
        "software_version",
        "hardware_version",
        "api_version",
    ):
        label = _safe_label(getattr(gateway, field, None))
        if label is not None and any(
            sensitive in label.casefold() for sensitive in sensitive_values
        ):
            label = "<redacted>"
        metadata[field] = label
    return metadata


async def async_collect_profile(
    client: SagemcomClient,
    *,
    authentication_method: str,
    benchmark_runs: int = 3,
) -> dict[str, object]:
    """Collect a shareable profile from an already authenticated client."""
    gateway = await client.get_device_info()
    capabilities, benchmark_paths = await _probe_metrics(client)
    schemas = await _probe_schemas(client)
    indexed_docsis = await _probe_indexed_docsis(client)
    benchmark = await _benchmark_reads(client, benchmark_paths, benchmark_runs)

    return {
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "privacy": {
            "read_only": True,
            "excluded": [
                "credentials",
                "router address",
                "gateway MAC address",
                "gateway serial number",
                "host and client data",
                "raw scalar metric values",
                "DOCSIS channel values and UIDs",
            ],
        },
        "gateway": _gateway_metadata(gateway, client),
        "authentication_method": _safe_label(authentication_method),
        "capabilities": capabilities,
        "schema_probes": schemas,
        "docsis_indexed_path_probes": indexed_docsis,
        "batch_benchmark": benchmark,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a read-only, privacy-safe Sagemcom capability profile. "
            "The password is never accepted as a command-line argument."
        )
    )
    parser.add_argument("--host", help="Router address; prompted when omitted")
    parser.add_argument("--username", help="Router username; prompted when omitted")
    parser.add_argument(
        "--encryption",
        choices=("MD5", "SHA512"),
        help="Known encryption method; auto-detected when omitted",
    )
    parser.add_argument("--ssl", action="store_true", help="Use HTTPS")
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Verify the router HTTPS certificate",
    )
    parser.add_argument(
        "--benchmark-runs",
        type=int,
        default=3,
        choices=range(1, 11),
        metavar="1-10",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this file instead of standard output",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing output file",
    )
    return parser


def _credential_value(
    argument: str | None,
    environment_name: str,
    prompt: str,
    *,
    hidden: bool = False,
) -> str:
    """Read one credential without ever echoing a password."""
    if argument is not None:
        return argument
    if environment_name in os.environ:
        return os.environ[environment_name]
    return getpass(prompt) if hidden else input(prompt).strip()


async def _run(args: argparse.Namespace) -> dict[str, object]:
    """Connect, authenticate, and collect one sanitized profile."""
    host = _credential_value(args.host, "SAGEMCOM_HOST", "Router address: ")
    username = _credential_value(
        args.username,
        "SAGEMCOM_USERNAME",
        "Router username (blank if not required): ",
    )
    password = _credential_value(
        None,
        "SAGEMCOM_PASSWORD",
        "Router password (hidden): ",
        hidden=True,
    )
    if not host:
        raise ValueError("A router address is required")

    configured_method = args.encryption or os.getenv("SAGEMCOM_ENCRYPTION")
    method = EncryptionMethod(configured_method.upper()) if configured_method else None
    client = SagemcomClient(
        host=host,
        username=username,
        password=password,
        authentication_method=method,
        ssl=args.ssl,
        verify_ssl=args.verify_ssl,
    )

    logged_in = False
    try:
        if method is None:
            print("Detecting router encryption method...", file=sys.stderr)
            method = await client.get_encryption_method()
            if method is None:
                raise RuntimeError("No supported encryption method detected")

        print("Authenticating and running read-only probes...", file=sys.stderr)
        await client.login()
        logged_in = True
        return await async_collect_profile(
            client,
            authentication_method=method.value,
            benchmark_runs=args.benchmark_runs,
        )
    finally:
        try:
            if logged_in:
                await client.logout()
        finally:
            await client.close()


def _write_profile(
    profile: Mapping[str, object],
    output: Path | None,
    *,
    overwrite: bool,
) -> None:
    """Write only the already-sanitized profile."""
    serialized = json.dumps(profile, indent=2, sort_keys=True, ensure_ascii=False)
    if output is None:
        print(serialized)
        return
    if output.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to replace {output}; use --overwrite if intended"
        )
    output.write_text(f"{serialized}\n", encoding="utf-8")
    print(f"Sanitized profile written to {output}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the privacy-safe contributor profile collector."""
    args = _parser().parse_args(argv)
    try:
        profile = asyncio.run(_run(args))
        _write_profile(profile, args.output, overwrite=args.overwrite)
    except KeyboardInterrupt:
        print("Probe cancelled.", file=sys.stderr)
        return 130
    except Exception as exception:  # pylint: disable=broad-except
        print(
            "Probe failed safely: "
            f"{json.dumps(_safe_error(exception), sort_keys=True)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
