from setuptools import setup, find_packages

setup(
    name="hpc_eff",
    version="0.1",
    description="Energy Optimization Governor",
    long_description_content_type="text/markdown",
    author="CESNET",
    license="GPL-3.0",
    python_requires=">=3.9",
    install_requires=[
        "numpy==2.0.2",
        "requests==2.32.4",
    ],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    keywords=["governor", "cpu", "frequency", "carbon intensity"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    ],
    entry_points={
        "console_scripts": [
            "hpc-eff = hpc_eff.main:main",
        ],
    },
    project_urls={
        "Repository": "https://gitlab.cesnet.cz/dexter/hpc_eff"
    },
)
