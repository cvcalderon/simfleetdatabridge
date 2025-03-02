import click
from simfleetdatabridge.app import EngineAgent
from simfleetdatabridge.transformer import transform_gtfs_to_json
from logger import logger

import spade
import asyncio
import signal
import sys

import requests


@click.group()
def cli():
    """CLI for managing SimfleetAI and LLM profile generation."""
    pass


@click.command(name="generate-llm-profiles")
@click.option("-input", 'input_path', type=click.Path(exists=True), required=True,
              help="Path to the input file containing profile data.")
@click.option("-output", 'output_path', type=click.Path(), required=True,
              help="Path to the output file where generated profiles will be saved.")
def generate_llm_profiles(input_path, output_path):
    """Generates LLM profiles based on input data."""
    logger.info(f'Generating LLM profiles from: {input_path}')

    # Placeholder for the actual profile generation logic
    # generate_llm_profiles(input_path, output_path)

    logger.success(f'LLM profiles generated and saved to: {output_path}')


@click.command(name="run-simfleetai")
@click.option("--base-dir", prompt="Base directory for simulations",
              help="Directory where the simulation is located or will be created.")
@click.option("--name", prompt="Simulation name",
              help="Name of the simulation to execute.")
@click.option("--framework-config", type=click.Path(exists=True), required=False,
              help="Path to the new framework_config.json file (optional).")
@click.option("--profiles", type=click.Path(exists=True), required=False,
              help="Path to profiles.json (optional, only needed when creating a new simulation).")
@click.option("--sim-config", type=click.Path(exists=True), required=False,
              help="Path to the Simfleet configuration file (optional, only needed when creating a new simulation).")



def main(task, input_path, output_path):
    """Runs the selected task based on user input."""

    #response = requests.post("http://ollama.gti-ia.upv.es/api/generate", json={"model": "llama3.3:70b", "prompt": "Your prompt here"})

    #print(response.text)

    #sys.exit(0)

    if task == "gtfs_to_json":
        click.echo(f'Processing GTFS file: {input_path}')
        transform_gtfs_to_json(input_path, output_path)
        click.echo(f'Generated JSON file: {output_path}')
    elif task == "generate_llm_profiles":
        click.echo(f'Generating LLM profiles from: {input_path}')
        #generate_llm_profiles(input_path, output_path)
        click.echo(f'Generated LLM profiles: {output_path}')
    elif task == "generate_decisions":
        click.echo(f'Generating decisions from: {input_path}')

        engine = app_engine(llm_conf=input_path, output=output_path)

    else:
        click.echo("Invalid task selected.")


    async def run_engine():
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)

        try:
            await engine.start()

            await engine.run()

            while not engine.is_finished():
                await asyncio.sleep(0.5)

            await engine.stop()

            sys.exit(0)

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            sys.exit(0)

    spade.run(run_engine())

def app_engine(llm_conf=None, output=None):

    instance = EngineAgent(config=llm_conf, output=output)

    return instance

if __name__ == '__main__':
    main()


