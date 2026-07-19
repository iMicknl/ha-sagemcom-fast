"""Home-Assistant-independent DOCSIS collection models and parsers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import TypeVar


@dataclass(frozen=True, slots=True)
class DocsisDownstreamChannel:
    """A validated downstream channel returned by the gateway."""

    uid: int
    channel_id: int
    lock_status: bool
    frequency: float | None
    bandwidth: int | None
    symbol_rate: int | None
    modulation: str | None
    snr: float | None
    power_level: float | None
    unerrored_codewords: int | None
    correctable_codewords: int | None
    uncorrectable_codewords: int | None


@dataclass(frozen=True, slots=True)
class DocsisUpstreamChannel:
    """A validated upstream channel returned by the gateway."""

    uid: int
    channel_id: int
    lock_status: bool
    frequency: float | None
    symbol_rate: int | None
    modulation: str | None
    power_level: float | None
    frequency31: str | None
    modulation31: str | None
    profile_id31: str | None


def _required_integer(item: Mapping[str, object], field: str) -> int:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return value


def _required_boolean(item: Mapping[str, object], field: str) -> bool:
    value = item.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return value


def _optional_integer(item: Mapping[str, object], field: str) -> int | None:
    if field not in item or item[field] is None:
        return None
    return _required_integer(item, field)


def _optional_float(item: Mapping[str, object], field: str) -> float | None:
    if field not in item or item[field] is None:
        return None
    value = item[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return normalized


def _optional_string(item: Mapping[str, object], field: str) -> str | None:
    if field not in item or item[field] is None:
        return None
    value = item[field]
    if not isinstance(value, str):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return value.strip() or None


def _parse_downstream(item: Mapping[str, object]) -> DocsisDownstreamChannel:
    return DocsisDownstreamChannel(
        uid=_required_integer(item, "uid"),
        channel_id=_required_integer(item, "channel_id"),
        lock_status=_required_boolean(item, "lock_status"),
        frequency=_optional_float(item, "frequency"),
        bandwidth=_optional_integer(item, "band_width"),
        symbol_rate=_optional_integer(item, "symbol_rate"),
        modulation=_optional_string(item, "modulation"),
        snr=_optional_float(item, "SNR"),
        power_level=_optional_float(item, "power_level"),
        unerrored_codewords=_optional_integer(item, "unerrored_codewords"),
        correctable_codewords=_optional_integer(item, "correctable_codewords"),
        uncorrectable_codewords=_optional_integer(item, "uncorrectable_codewords"),
    )


def _parse_upstream(item: Mapping[str, object]) -> DocsisUpstreamChannel:
    return DocsisUpstreamChannel(
        uid=_required_integer(item, "uid"),
        channel_id=_required_integer(item, "channel_id"),
        lock_status=_required_boolean(item, "lock_status"),
        frequency=_optional_float(item, "frequency"),
        symbol_rate=_optional_integer(item, "symbol_rate"),
        modulation=_optional_string(item, "modulation"),
        power_level=_optional_float(item, "power_level"),
        frequency31=_optional_string(item, "frequency31"),
        modulation31=_optional_string(item, "modulation31"),
        profile_id31=_optional_string(item, "profile_id31"),
    )


_ChannelT = TypeVar("_ChannelT")


def _parse_collection(
    value: object,
    parser: Callable[[Mapping[str, object]], _ChannelT],
) -> tuple[_ChannelT, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid DOCSIS collection: {type(value).__name__}")

    channels: list[_ChannelT] = []
    seen_uids: set[int] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        try:
            channel = parser(item)
        except ValueError:
            continue
        uid = getattr(channel, "uid")
        if uid in seen_uids:
            raise ValueError(f"Duplicate DOCSIS channel uid: {uid}")
        seen_uids.add(uid)
        channels.append(channel)

    if value and not channels:
        raise ValueError("DOCSIS collection contains no valid channels")
    return tuple(channels)


def parse_docsis_downstream_channels(
    value: object,
) -> tuple[DocsisDownstreamChannel, ...]:
    """Validate a downstream collection while skipping malformed items."""
    return _parse_collection(value, _parse_downstream)


def parse_docsis_upstream_channels(
    value: object,
) -> tuple[DocsisUpstreamChannel, ...]:
    """Validate an upstream collection while skipping malformed items."""
    return _parse_collection(value, _parse_upstream)
