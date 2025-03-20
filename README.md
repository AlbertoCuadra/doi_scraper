# DOI Scraper

The DOI Scraper is a Python script that reads a `.bib` file, searches for entries missing required fields (such as a DOI), retrieves the missing information using the [Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), and reformats the file with consistent indentation. The refactored design supports different entry types (e.g., articles, books, inproceedings, tech reports), with each type defining its own required fields.

## Prerequisites

- Python 3.x
- `requests` library
- `tqdm` library

## Installation

1. Clone the repository or download the `doi_scraper.py` file.

2. Install the required dependencies by running the following command:

```shell
pip install -r requirements.txt
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

## Optional Arguments

* `--format-only`: If you want to reformat the file without performing any Crossref lookups, pass the --format-only flag:

```shell
python doi_scraper.py --format-only
```

# Example

## Before

```bibtex
@article{Cuadra2020,
title            = {Effect of equivalence ratio fluctuations on planar detonation discontinuities},
author   = {Cuadra, Alberto and Huete, C{\'e}sar and Vera, Marcos},
pages= {A30 1--39}
}
```

## After

```bibtex
@article{Cuadra2020,
    title           = {Effect of equivalence ratio fluctuations on planar detonation discontinuities},
    author          = {Cuadra, Alberto and Huete, C{\'e}sar and Vera, Marcos},
    pages           = {A30 1--39},
    year            = {2020},
    journal         = {Journal of Fluid Mechanics},
    volume          = {903},
    doi             = {10.1017/jfm.2020.651},
}
```

# License

This project is licensed under the [MIT License](LICENSE).