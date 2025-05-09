from setuptools import setup, find_packages

setup(
    name="firmware_upgrader",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "paramiko>=3.0.0",
        "python-dotenv>=1.0.0",
        "tftpy==0.8.5"
    ],
    python_requires=">=3.6",
) 