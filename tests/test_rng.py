from collections import Counter

import pytest

from edge_engine.rng import Rng, SplitMix64


def test_splitmix64_reference_values():
    sm = SplitMix64(0)
    assert [sm.next_u64() for _ in range(3)] == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
    ]


def test_xoshiro256starstar_reference_values():
    # Same vector as the reference tests of the rand_xoshiro crate.
    rng = Rng.from_state([1, 2, 3, 4])
    assert [rng.next_u64() for _ in range(6)] == [
        11520,
        0,
        1509978240,
        1215971899390074240,
        1216172134540287360,
        607988272756665600,
    ]


def test_same_seed_same_stream():
    a, b = Rng(42), Rng(42)
    assert [a.next_u64() for _ in range(100)] == [b.next_u64() for _ in range(100)]


def test_different_seeds_differ():
    assert Rng(1).next_u64() != Rng(2).next_u64()


def test_state_roundtrip_replays():
    rng = Rng(7)
    for _ in range(10):
        rng.next_u64()
    saved = rng.getstate()
    first = [rng.random() for _ in range(5)]
    rng.setstate(saved)
    assert [rng.random() for _ in range(5)] == first


@pytest.mark.parametrize("bad", [-1, 1.5, "3", True])
def test_bad_seed(bad):
    with pytest.raises(ValueError):
        Rng(bad)


def test_zero_state_rejected():
    with pytest.raises(ValueError):
        Rng.from_state([0, 0, 0, 0])


def test_random_in_unit_interval():
    rng = Rng(3)
    xs = [rng.random() for _ in range(10_000)]
    assert all(0.0 <= x < 1.0 for x in xs)
    assert abs(sum(xs) / len(xs) - 0.5) < 0.02  # SE is about 0.003


def test_randbelow_range_and_errors():
    rng = Rng(5)
    assert {rng.randbelow(7) for _ in range(2000)} == set(range(7))
    assert rng.randbelow(1) == 0
    assert 0 <= rng.randbelow(1 << 64) < 1 << 64
    with pytest.raises(ValueError):
        rng.randbelow(0)
    with pytest.raises(ValueError):
        rng.randbelow((1 << 64) + 1)


def test_randint_uniform_chi_square():
    rng = Rng(11)
    n = 60_000
    counts = Counter(rng.randint(1, 6) for _ in range(n))
    expected = n / 6
    chi2 = sum((counts[f] - expected) ** 2 / expected for f in range(1, 7))
    assert chi2 < 20.5  # 99.9th percentile of chi-square with 5 degrees of freedom


def test_shuffle_is_permutation_and_seeded():
    a, b = list(range(52)), list(range(52))
    Rng(9).shuffle(a)
    Rng(9).shuffle(b)
    assert a == b
    assert sorted(a) == list(range(52))
    assert a != list(range(52))


def test_shuffle_all_orders_equally_likely():
    rng = Rng(13)
    n = 24_000
    counts = Counter()
    for _ in range(n):
        items = [0, 1, 2]
        rng.shuffle(items)
        counts[tuple(items)] += 1
    assert len(counts) == 6
    expected = n / 6
    chi2 = sum((c - expected) ** 2 / expected for c in counts.values())
    assert chi2 < 20.5


def test_sample_distinct():
    rng = Rng(2)
    s = rng.sample(range(10), 4)
    assert len(s) == len(set(s)) == 4
    assert rng.sample([], 0) == []
    with pytest.raises(ValueError):
        rng.sample([1, 2], 3)


def test_choice_and_bernoulli():
    rng = Rng(4)
    assert rng.choice("abc") in "abc"
    with pytest.raises(IndexError):
        rng.choice([])
    hits = sum(rng.bernoulli(0.3) for _ in range(20_000))
    assert abs(hits / 20_000 - 0.3) < 0.015
    assert not any(rng.bernoulli(0.0) for _ in range(100))
    assert all(rng.bernoulli(1.0) for _ in range(100))
