import pytest

from app.keys import key_name, to_camelot, wheel_order


@pytest.mark.parametrize("key,expected", [
    ("A minor", "8A"), ("Am", "8A"), ("C major", "8B"), ("C", "8B"), ("F# minor", "11A"),
    ("Gb major", "2B"), ("Bb minor", "3A"), ("E♭ major", "5B"), ("8A", "8A"), ("12b", "12B"),
])
def test_to_camelot(key, expected):
    assert to_camelot(key) == expected


def test_to_camelot_rejects_garbage():
    assert to_camelot("nonsense") is None
    assert to_camelot(None) is None


def test_key_names_and_wheel_order():
    assert key_name("8A") == "A minor" and key_name("8B") == "C major" and key_name(None) is None
    assert sorted(["10A", "2B", "2A", "1B"], key=wheel_order) == ["1B", "2A", "2B", "10A"]
