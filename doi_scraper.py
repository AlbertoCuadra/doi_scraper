# This script searches for missing DOIs in a .bib file
# and fills them in using the Crossref API.
#
# Dependencies:
#    * requests
#
# Example:
#    python doi_scraper.py
#
# @author: Alberto Cuadra Lara
#          PhD Candidate - Group Fluid Mechanics
#          Universidad Carlos III de Madrid
#                  
# Last update May 13 2023

import re
import requests

# Definitions
input_file = 'input.bib'   # Input .bib file
output_file = 'output.bib' # Output .bib file
INDENT_PRE = 4             # Number of spaces before the field name
INDENT_POST = 16           # Number of spaces after the field name


# Function that prepares a given title for comparison
def prepare_title(title):
    title = title.lower()
    title = re.sub(r'[–‐]', '-', title)
    title = re.sub(r'--', '-', title)
    return title

# Function to get DOI based on article title
def get_doi(title):
    # Set request
    api_url = 'https://api.crossref.org/works'
    query = f'query.bibliographic={title}&rows=3'  # Get up to 3 results
    url = f'{api_url}?{query}'
    response = requests.get(url)
    # Get response
    data = response.json()
    
    if 'items' in data['message'] and len(data['message']['items']) > 0:
        # Sort items by published date (newest first)
        items = sorted(data['message']['items'], key=lambda x: x.get('created', {}).get('date-time'), reverse=True)
        
        # Prepare title for comparison
        title_lower = prepare_title(title)
        
        # Search for DOI
        for item in items:
            item_title = item.get('title', [''])[0]
            
            # Prepare title for comparison
            item_title_lower = prepare_title(item_title)

            # print('Comparing:\n', title_lower, '\n', item_title_lower, '\n') # (debug)
            
            # Compare titles
            if title_lower in item_title_lower:
                doi = item['DOI']
                if not doi.endswith('.vid'):
                    return doi
        
    return ''

def process_bib_line(line, current_item):
    if line.startswith('@'):
        if current_item:
            updated_bib_data.append(current_item.strip())
        current_item = line.strip()
        return current_item
    
    if current_item and line.startswith('}'):
        if 'doi' not in current_item.lower() and '@book' not in current_item.lower():
            title_match = title_regex.search(current_item)
            if title_match:
                title = title_match.group(1).strip()
                # Remove additional curly braces
                title = re.sub(r'[{}]', '', title)
                # Get doi
                doi = get_doi(title)
                if doi:
                    # Adjusted indentation for field name
                    indent = ' ' * INDENT_PRE
                    # Adjusted indentation for field line
                    field_line = f'{indent}doi{" " * (INDENT_POST - 3)} = {{{doi}}}'
                    # Append DOI field with indentation
                    current_item += ',\n' + field_line 
                    # Print DOI found
                    print('DOI found for article:', title, '->', doi)
                else:
                    # Print DOI not found
                    print('DOI not found for article:', title)
        
        current_item += '\n' + line.strip()
        updated_bib_data.append(current_item)
        current_item = ''
    else:
        if '=' in line:
            field_name, field_value = line.split('=', 1)
            field_name = field_name.strip()
            field_value = field_value.strip()
            indent = ' ' * (INDENT_POST - len(field_name))
            line = f'{field_name} {indent}= {field_value}'
        current_item += '\n' + ' ' * INDENT_PRE + line.strip()
    
    return current_item


# Compile the regular expressions
title_regex = re.compile(r'title\s*=\s*\{([^}]*)\}')

with open(input_file, 'r') as f:
    bib_data = f.readlines()

# Search and fill missing DOIs
updated_bib_data = []
current_item = ''

for line in bib_data:
    current_item = process_bib_line(line, current_item)

# Save the updated .bib file
if current_item:
    updated_bib_data.append(current_item.strip())

updated_bib_content = '\n'.join(updated_bib_data)

with open(output_file, 'w') as f:
    f.write(updated_bib_content)

print('Updated .bib file saved as', output_file)
