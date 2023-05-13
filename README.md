# DOI Scraper

The DOI Scraper is a Python script that reads a `.bib` file, searches for articles without a DOI (Digital Object Identifier), and retrieves the missing DOIs using the [Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/). It then updates the `.bib` file with the retrieved DOIs.

## Prerequisites

* Python
* `requests` library

## Installation

1. Clone the repository or download the `doi_scraper.py` file.

2. Install the required dependencies by running the following command:

```shell
pip install requests
```

# Usage

Place your input `.bib` file in the same directory as the `doi_scraper.py` script.

Open the `doi_scraper.py` file and modify the following variables according to your needs:

```python
input_file = 'input.bib'   # Name of the input .bib file
output_file = 'output.bib' # Name of the output .bib file
INDENT_PRE = 4             # Number of spaces before the field name
INDENT_POST = 16           # Number of spaces after the field name
```

Run the script using the following command:

```shell
python doi_scraper.py
```

The script will search for articles without a DOI and retrieve the missing DOIs using the Crossref API. It will then update the output .bib file with the retrieved DOIs.

Once the script completes, you will find the updated .bib file with the retrieved DOIs in the same directory.

# Example

## Before

```bibtex
@article{Cuadra2020,
title            = {Effect of equivalence ratio fluctuations on planar detonation discontinuities},
author   = {Cuadra, Alberto and Huete, C{\'e}sar and Vera, Marcos},
year    = 2020,
journal  = {Journal of Fluid Mechanics},
publisher    = {Cambridge University Press},
volume       = 903,
pages= {A30 1--39}
}
```

## After

```bibtex
@article{Cuadra2020,
    title            = {Effect of equivalence ratio fluctuations on planar detonation discontinuities},
    author           = {Cuadra, Alberto and Huete, C{\'e}sar and Vera, Marcos},
    year             = 2020,
    journal          = {Journal of Fluid Mechanics},
    publisher        = {Cambridge University Press},
    volume           = 903,
    pages            = {A30 1--39},
    doi              = {10.1017/jfm.2020.651}
}
```

# License

This project is licensed under the [MIT License](LICENSE).