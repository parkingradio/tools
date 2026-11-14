import click
import pytest

from parkingradio import site


@pytest.mark.parametrize(
    ("value", "address"),
    [
        ("https://parking.radio", "https://parking.radio"),
        ("https://parking.radio/", "https://parking.radio"),
        ("HTTPS://Parking.Radio", "https://parking.radio"),
        ("https://test.parking.radio:8443", "https://test.parking.radio:8443"),
        ("http://localhost:5173", "http://localhost:5173"),
        ("http://LOCALHOST:5173/", "http://localhost:5173"),
    ],
)
def test_parse(value, address):
    assert site.parse(value) == address


@pytest.mark.parametrize(
    "value",
    [
        "parking.radio",
        "ftp://parking.radio",
        "https://",
        "https://parking.radio/admin",
        "https://parking.radio?x=1",
        "https://parking.radio/?",
        "https://parking.radio#top",
        "https://user@parking.radio",
        "https://parking.radio:port",
        "http://parking.radio",
        "http://127.0.0.1:5173",
    ],
)
def test_parse_refuses(value):
    with pytest.raises(click.BadParameter):
        site.parse(value)
