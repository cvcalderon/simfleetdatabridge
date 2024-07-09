import click
from simfleetdatabridge.transformer import transform_gtfs_to_json

@click.command()
@click.option("-input", 'zip_file_path', type=click.Path(exists=True), help="File path of zip file")
@click.option("-output", 'output_path', type=click.Path(), help="File path of json file")
def main(zip_file_path, output_path):
    """Transforms a GTFS file to a JSON file for SimFleet."""
    click.echo(f'Processing GTFS file: {zip_file_path}')
    transform_gtfs_to_json(zip_file_path, output_path)
    click.echo(f'Generated JSON file: {output_path}')

if __name__ == '__main__':
    main()
