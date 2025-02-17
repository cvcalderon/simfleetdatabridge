from setuptools import setup, find_packages

with open("README.rst") as readme_file:
    readme = readme_file.read()

def parse_requirements(filename):
    """ load requirements from a pip requirements file """
    with open(filename) as f:
        lineiter = (line.strip() for line in f)
        return [line for line in lineiter if line and not line.startswith("#")]

requirements = parse_requirements("requirements.txt")

setup(
    name='SimfleetDataBridge',
    version='0.1.0',
    author="Christian Calderón Orellana",
    author_email="cvcalderon@gmail.com",
    url="https://github.com/cvcalderon/simfleetdatabridge",
    packages=find_packages(include=["simfleetdatabridge"]),
    install_requires=requirements,
    license="MIT license",
    entry_points={"console_scripts": ["SimfleetDataBridge=simfleetdatabridge.cli:main"]},
    keywords="simfleetdatabridge",
)