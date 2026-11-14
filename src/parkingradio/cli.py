import click


@click.group(name="parkingradio")
@click.version_option(package_name="parkingradio")
def main() -> None:
    """Tools that automate operating Parking Radio."""
