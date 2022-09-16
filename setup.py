import re
from pathlib import Path

import pkg_resources as pkg
from setuptools import find_packages, setup

# Settings
FILE = Path(__file__).resolve()
ROOT = FILE.parent  # root directory
README = (ROOT / "README.md").read_text(encoding="utf-8")
REQUIREMENTS = [f'{x.name}{x.specifier}' for x in pkg.parse_requirements((ROOT / 'requirements.txt').read_text())]


def get_version():
    file = ROOT / 'ultralytics/__init__.py'
    return re.search(r'^__version__ = [\'"]([^\'"]*)[\'"]', file.read_text(), re.M)[1]


setup(
    name="ultralytics",  # name of pypi package
    version=get_version(),  # version of pypi package
    python_requires=">=3.7.0",
    long_description=README,
    long_description_content_type="text/markdown",
    # url="https://github.com/ultralytics/ultralytics",
    project_urls={
        'Bug Reports': 'https://github.com/ultralytics/ultralytics/issues',
        'Funding': 'https://ultralytics.com',
        'Source': 'https://github.com/ultralytics/ultralytics',},
    author="Ultralytics",
    author_email='hello@ultralytics.com',
    # package_dir={'': 'ultralytics'},  # Optional, use if source code is in a subdirectory under the project root, i.e. `src/`
    packages=find_packages('ultralytics'),  # required
    include_package_data=True,
    install_requires=REQUIREMENTS,
    extras_require={
        'dev': ['check-manifest'],
        'test': ['pytest', 'pytest-cov', 'coverage'],},
    classifiers=[
        "Intended Audience :: Developers", "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)", "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7", "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9", "Programming Language :: Python :: 3.10",
        "Topic :: Software Development", "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Image Recognition", "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS", "Operating System :: Microsoft :: Windows"],
    keywords="machine-learning, deep-learning, ML, DL, AI, PyTorch, vision, YOLO, YOLOv3, YOLOv5, YOLOv8, HUB, Ultralytics")
