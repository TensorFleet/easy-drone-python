#!/usr/bin/env python3
"""
Setup script for gz-transport-py with integrated gz-msgs
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gz-transport-py",
    version="0.1.0",
    author="Your Name",
    description="Pure Python implementation of Gazebo Transport with integrated gz-msgs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/gz-transport-py",
    packages=find_packages(include=['gz_transport_py', 'gz_transport_py.*', 'gz', 'gz.*']),
    package_data={
        'gz.msgs': ['*.py', '*.pyi'],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Robotics",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pyzmq>=25.0.0",
        "protobuf>=4.21.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "mypy-protobuf>=3.0.0",
        ],
    },
    zip_safe=False,
    include_package_data=True,
)

