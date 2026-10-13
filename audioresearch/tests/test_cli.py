import pytest

from audioresearch.cli import _levels, build_parser


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    assert all(c in out for c in ("research", "review", "report"))


def test_levels():
    assert _levels("0-5") == [0, 1, 2, 3, 4, 5]
    assert _levels("1,3") == [1, 3]
