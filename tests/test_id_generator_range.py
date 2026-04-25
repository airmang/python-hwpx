from __future__ import annotations

from hwpx.oxml.document import _memo_id, _object_id, _paragraph_id


_GENERATORS = (_paragraph_id, _object_id, _memo_id)


def test_id_generators_stay_within_signed_int32() -> None:
    """Generated IDs must fit in signed int32 so downstream consumers that
    parse the ``id`` attribute as ``int`` see a non-negative value."""

    for gen in _GENERATORS:
        for _ in range(200):
            value = int(gen())
            assert 0 <= value < 2**31, (
                f"{gen.__name__} produced {value} (0x{value:x}); "
                "must be in [0, 2^31)"
            )


def test_id_generators_use_full_31_bit_range() -> None:
    """The generators should still draw from a wide range so collisions
    remain negligible. Sample 4_000 values and require at least one above
    2^30 to guard against accidental over-restriction."""

    for gen in _GENERATORS:
        samples = [int(gen()) for _ in range(4000)]
        assert max(samples) >= 2**30, (
            f"{gen.__name__} samples capped at {max(samples):#x}; "
            "expected the full [0, 2^31) range"
        )
