"""Setup configuration for VoIP Analyzer."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="voip-analyzer",
    version="0.1.0",
    author="VoIP Analyzer Contributors",
    description="Analyze VoIP call quality from PCAP files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/voip-analyzer",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "scapy>=2.5.0",
        "rich>=13.7.0",
        "click>=8.1.7",
        "numpy>=1.26.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-cov>=4.1.0",
            "black>=23.12.0",
            "mypy>=1.7.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "voip-analyzer=voip_analyzer.main:cli",
        ],
    },
)
