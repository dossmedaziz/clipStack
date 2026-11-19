"""Packaging for ClipStack (used by dh-python / pybuild)."""

import re
from pathlib import Path

from setuptools import setup

version = re.search(r'__version__ = "([^"]+)"',
                    Path("clipstack/__init__.py").read_text(encoding="utf-8")).group(1)

setup(
    name="clipstack",
    version=version,
    description="Win+V style clipboard history for Ubuntu",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="dosss",
    author_email="dossaziz4@gmail.com",
    license="MIT",
    packages=["clipstack"],
    python_requires=">=3.10",
    entry_points={"console_scripts": ["clipstack = clipstack.__main__:main"]},
    classifiers=[
        "Environment :: X11 Applications :: GTK",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: Desktop Environment",
    ],
)
