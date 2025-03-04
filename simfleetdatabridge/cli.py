import click
from simfleetdatabridge.app import EngineAgent
from loguru import logger

import spade
import asyncio
import signal
import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime


@click.group()
def main():
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
def run_simfleetai(base_dir, name, framework_config, profiles, sim_config):
    """Runs a simulation with SimfleetAI, creating or loading the simulation as needed."""

    sim_path = Path(base_dir) / name
    is_new_simulation = not sim_path.exists()

    if is_new_simulation:
        logger.info(f"Simulation '{name}' not found. Creating a new one...")

        if not framework_config or not profiles or not sim_config:
            logger.error(
                "To create a new simulation, you must provide --framework-config, --profiles, and --sim-config.")
            sys.exit(1)

        # Create directory structure using Path
        (sim_path / "config/simfleet").mkdir(parents=True, exist_ok=True)
        (sim_path / "agents/decisions").mkdir(parents=True, exist_ok=True)
        (sim_path / "metrics/days").mkdir(parents=True, exist_ok=True)

        # Configure loguru to write logs to the simulation log file
        log_file = sim_path / "simulation.log"
        logger.add(str(log_file), rotation="10 MB", retention="10 days", level="INFO")

        # Copy framework_config.json
        shutil.copy(framework_config, sim_path / "config/framework_config.json")

        # Move profiles.json and memory.json to agents/
        shutil.copy(profiles, sim_path / "agents/profiles.json")

        # Create an empty memory.json if it doesn't exist
        memory_path = sim_path / "agents/memory.json"
        if not memory_path.exists():
            with open(memory_path, "w") as f:
                json.dump({}, f, indent=4)

        # Rename and move the sim-config file to simfleet/
        sim_config_name = Path(sim_config).name
        new_sim_config_name = f"0_day_{sim_config_name}"
        new_sim_config_path = sim_path / "config/simfleet" / new_sim_config_name

        shutil.copy(sim_config, new_sim_config_path)

        # Generate dynamic creation date
        creation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Save simulation metadata
        metadata = {
            "name": name,
            "base_directory": str(base_dir),
            "full_path": str(sim_path),
            "created_at": creation_date,
            "status": "initialized"
        }
        with open(sim_path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=4)

        logger.success(f"New simulation '{name}' created in {sim_path}")
        logger.info(f"Simfleet configuration file saved as: {new_sim_config_path}")

    else:
        logger.info(f"Loading existing simulation '{name}' from {sim_path}")

    # Start the decision-making engine
    engine = app_engine(base_dir, name, framework_config)

    asyncio.run(run_engine(engine))


async def run_engine(engine):
    """Runs the simulation engine asynchronously."""
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    try:
        await engine.start()
        await engine.run()

        while not engine.is_finished():
            await asyncio.sleep(0.5)

        await engine.stop()
        logger.success("Simulation completed successfully.")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Error during execution: {e}")
        sys.exit(1)


def app_engine(base_dir, name, framework_config):
    """Creates a simulation engine instance using base_dir, name, and framework_config."""
    sim_path = Path(base_dir) / name

    if not sim_path.exists():
        logger.error(f"Simulation '{name}' not found in '{base_dir}'.")
        sys.exit(1)

    framework_config_path = sim_path / "config/framework_config.json"

    # If a new framework_config.json is provided, copy it to the simulation directory
    if framework_config:
        shutil.copy(framework_config, framework_config_path)
        logger.info(f"Configuration file updated at: {framework_config_path}")

    # Create the simulation engine instance
    instance = EngineAgent(config=str(framework_config_path), sim_path=str(sim_path))
    logger.info(f"Simulation engine initialized for '{name}' in '{sim_path}'")

    return instance


# Add commands to the CLI group
main.add_command(generate_llm_profiles)
main.add_command(run_simfleetai)

if __name__ == '__main__':
    main()




