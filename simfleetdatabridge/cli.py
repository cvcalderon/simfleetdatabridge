import click
from simfleetdatabridge.app import EngineAgent
from simfleetdatabridge.transformer import transform_gtfs_to_json
from logger import logger

import spade
import asyncio
import signal
import sys

import requests


@click.command()
@click.option(
    "--task",
    type=click.Choice(["gtfs_to_json", "generate_llm_profiles", "generate_decisions"], case_sensitive=False),
    required=True,
    help="Task to perform: 'gtfs_to_json', 'generate_llm_profiles', or 'generate_decisions'."
)
@click.option("-input", 'input_path', type=click.Path(exists=True), help="File path for input")
@click.option("-output", 'output_path', type=click.Path(), help="File path for output")


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


