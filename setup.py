"""Setup script for mimo-cli."""

from setuptools import setup, find_packages

setup(
    name="mimo-cli",
    version="1.0.0",
    description="Automated Xiaomi MiMo account creation CLI tool with referral bonuses",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="rapoii",
    url="https://github.com/rapoii/mimo-cli",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "patchright",
        "SpeechRecognition",
        "pydub",
    ],
    entry_points={
        "console_scripts": [
            "mimo=mimo_cli.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Testing",
    ],
)
