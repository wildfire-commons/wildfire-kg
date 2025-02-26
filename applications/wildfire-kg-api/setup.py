from setuptools import setup, find_packages
import os


# Read requirements
def read_requirements(filename):
    with open(filename) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("-r") and not line.startswith("#")
        ]


# Get base requirements
base_requirements = read_requirements("requirements.txt")

# Get dev requirements (excluding base requirements which are included via -r)
dev_requirements = [
    req for req in read_requirements("requirements-dev.txt") if not req.startswith("-r")
]

setup(
    name="wildfire-kg-api",
    version="0.1.0",
    description="Wildfire Knowledge Graph API with LangGraph integration",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    include_package_data=True,
    install_requires=base_requirements,
    extras_require={
        "dev": dev_requirements,
    },
    entry_points={
        "console_scripts": [
            "wkg=src.main:cli",
        ],
    },
    python_requires=">=3.9",
)
