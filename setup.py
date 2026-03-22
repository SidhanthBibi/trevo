"""Package setup for trevo — voice-to-text desktop application."""

from pathlib import Path

from setuptools import find_packages, setup

_HERE = Path(__file__).resolve().parent

# Read requirements.txt
_requirements: list[str] = []
_req_path = _HERE / "requirements.txt"
if _req_path.exists():
    _requirements = [
        line.strip()
        for line in _req_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


setup(
    name="trevo",
    version="1.0.0",
    description="Voice-to-text desktop application with AI-powered text polishing",
    long_description=(_HERE / "README.md").read_text(encoding="utf-8")
    if (_HERE / "README.md").exists()
    else "",
    long_description_content_type="text/markdown",
    author="Sidharth",
    author_email="",
    license="MIT",
    url="https://github.com/sidharth/trevo",
    python_requires=">=3.11",
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    install_requires=_requirements,
    entry_points={
        "console_scripts": [
            "trevo=main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Win32 (MS Windows)",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
    ],
)
