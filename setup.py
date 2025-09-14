#!/usr/bin/env python3
"""Setup script for Shopify Product Uploader"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="shopify-product-uploader",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Automated product migration from ERPNext to Shopify with AI SEO optimization",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/shopify-product-uploader",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.11",
    install_requires=[
        "python-dotenv==1.0.1",
        "requests==2.32.3",
        "beautifulsoup4==4.12.3",
        "lxml==5.3.0",
        "tenacity==9.0.0",
        "openai==1.35.0",
        "shopifyapi==12.5.0",
        "colorama==0.4.6",
        "tabulate==0.9.0",
        "jsonlines==4.0.0",
        "ratelimit==2.2.1",
    ],
    extras_require={
        "dev": [
            "pytest==8.3.3",
            "pytest-mock==3.14.0",
            "pytest-asyncio==0.24.0",
            "responses==0.25.3",
        ]
    },
    entry_points={
        "console_scripts": [
            "shopify-uploader=main:main",
        ],
    },
)