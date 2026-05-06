import pytest

from pomocli.utils.text import normalize_display_name


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("my project", "My Project"),
        ("MY PROJECT", "MY PROJECT"),
        ("my API", "My API"),
        ("NuCLEAR", "NuCLEAR"),
        ("iOS app", "iOS App"),
        ("the journey of a dev", "The Journey of a Dev"),
        ("refactor auth for nuclear", "Refactor Auth for Nuclear"),
        ("  multi   space  ", "Multi Space"),
        ("a", "A"),
        ("the", "The"),
        ("of", "Of"),
        ("API", "API"),
        ("API gateway", "API Gateway"),
        ("auth vs db", "Auth vs Db"),
    ],
)
def test_normalize_display_name(raw, expected):
    assert normalize_display_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_normalize_display_name_empty(raw):
    assert normalize_display_name(raw) == ""
