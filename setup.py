#!/usr/bin/env python3
"""
Setup script for easy-drone - Pure Python Gazebo Transport implementation
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="easy-drone",
    version="0.1.0",
    author="Easy Drone Contributors",
    description="Pure Python implementation of Gazebo Transport for easy drone communication",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/TensorFleet/easy-drone-python",
    packages=find_packages(
        include=['gz_transport', 'gz_transport.*', 'gz', 'gz.*']),
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
        "protobuf>=4.25.0",  # Requires runtime_version support
    ],
    extras_require={
        "zenoh": [
            "eclipse-zenoh",
        ],
        "yolo": [
            "opencv-python>=4.5.0",
            "numpy>=1.21.0",
            "onnxruntime>=1.12.0",
            "matplotlib>=3.5.0",
        ],
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
