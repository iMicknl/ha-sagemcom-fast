"""Tests for Home-Assistant-independent DOCSIS collection parsing."""

from __future__ import annotations

import pytest

from custom_components.sagemcom_fast.docsis import (
    DocsisDownstreamChannel,
    DocsisUpstreamChannel,
    parse_docsis_downstream_channels,
    parse_docsis_upstream_channels,
)


def test_downstream_collection_normalizes_known_channel_fields() -> None:
    channels = parse_docsis_downstream_channels(
        [
            {
                "uid": 4,
                "channel_id": 12,
                "lock_status": True,
                "frequency": 314.0,
                "band_width": 8,
                "symbol_rate": 6952,
                "modulation": " QAM256 ",
                "SNR": 40.2,
                "power_level": 2.4,
                "unerrored_codewords": 1000,
                "correctable_codewords": 3,
                "uncorrectable_codewords": 1,
            }
        ]
    )

    assert channels == (
        DocsisDownstreamChannel(
            uid=4,
            channel_id=12,
            lock_status=True,
            frequency=314.0,
            bandwidth=8,
            symbol_rate=6952,
            modulation="QAM256",
            snr=40.2,
            power_level=2.4,
            unerrored_codewords=1000,
            correctable_codewords=3,
            uncorrectable_codewords=1,
        ),
    )


def test_upstream_collection_normalizes_docsis_31_fields() -> None:
    channels = parse_docsis_upstream_channels(
        [
            {
                "uid": 8,
                "channel_id": 3,
                "lock_status": True,
                "frequency": 42.0,
                "symbol_rate": 5120,
                "modulation": "QAM64",
                "power_level": 43.5,
                "frequency31": "",
                "modulation31": "OFDMA",
                "profile_id31": "2",
            }
        ]
    )

    assert channels == (
        DocsisUpstreamChannel(
            uid=8,
            channel_id=3,
            lock_status=True,
            frequency=42.0,
            symbol_rate=5120,
            modulation="QAM64",
            power_level=43.5,
            frequency31=None,
            modulation31="OFDMA",
            profile_id31="2",
        ),
    )


def test_collection_skips_a_malformed_item_when_valid_channels_remain() -> None:
    channels = parse_docsis_downstream_channels(
        [
            {"uid": "bad", "channel_id": 1, "lock_status": True},
            {"uid": 2, "channel_id": 2, "lock_status": False},
        ]
    )

    assert [channel.uid for channel in channels] == [2]
    assert channels[0].frequency is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [{"uid": 1, "channel_id": 1}],
        [{"uid": True, "channel_id": 1, "lock_status": True}],
    ],
)
def test_collection_rejects_invalid_shapes(value: object) -> None:
    with pytest.raises(ValueError):
        parse_docsis_downstream_channels(value)


def test_collection_rejects_duplicate_channel_uids() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        parse_docsis_upstream_channels(
            [
                {"uid": 1, "channel_id": 1, "lock_status": True},
                {"uid": 1, "channel_id": 2, "lock_status": True},
            ]
        )
