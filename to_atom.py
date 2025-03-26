import sys
import click
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from lxml import etree
import copy
import os

def parse_timestamp(title_attr):
    """
    Parse timestamp from title attribute like 'Mar 13, 2025 12:39 PM UTC'.
    Returns a timezone-aware datetime object.
    """
    if not title_attr:
        # Default to current UTC time if no attribute provided
        return datetime.now(timezone.utc)

    try:
        # Parse the string and make it timezone-aware (assuming UTC)
        dt_naive = datetime.strptime(title_attr, "%b %d, %Y %I:%M %p %Z")
        dt_aware = dt_naive.replace(tzinfo=timezone.utc)
        return dt_aware
    except ValueError:
        # Default to current UTC time if unable to parse
        # Log this potential issue? For now, just return current time.
        print(f"Warning: Could not parse timestamp '{title_attr}'. Defaulting to now.", file=sys.stderr)
        return datetime.now(timezone.utc)


def create_base_feed_and_entries(soup, base_url):
    """
    Parses HTML, creates the base Atom feed structure, and extracts entry data.
    Returns the base feed element (without entries) and a list of tuples:
    [(datetime_updated, entry_element)].
    """
    # Create the root element for the feed
    feed = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")

    # Add feed metadata
    ET.SubElement(feed, "title").text = "Ollama models"
    ET.SubElement(feed, "id").text = base_url
    author = ET.SubElement(feed, "author")
    ET.SubElement(author, "name").text = "Model Library"
    ET.SubElement(feed, "link", href=base_url, rel="self")
    # Add a general updated time for the feed itself (last checked time)
    ET.SubElement(feed, "updated").text = datetime.now(timezone.utc).isoformat()

    # Find all model items
    models = soup.find_all("li", attrs={"x-test-model": True})
    entries_data = []

    for model in models:
        entry = ET.Element("entry")

        # Get the model name
        title_elem = model.find("span", attrs={"x-test-search-response-title": True})
        title = title_elem.text if title_elem else "Unknown Model"
        ET.SubElement(entry, "title").text = title

        # Get the model URL
        href = model.find("a")["href"] if model.find("a") else ""
        model_url = urljoin(base_url, href)
        ET.SubElement(entry, "id").text = model_url
        ET.SubElement(entry, "link", href=model_url)

        # Get the model description
        description_elem = model.find("p", class_="max-w-lg")
        description = description_elem.text.strip() if description_elem else ""
        ET.SubElement(entry, "summary").text = description

        # Get updated time from the title attribute
        date_span = model.find("span", class_="flex items-center", title=True)
        title_attr = date_span.get("title") if date_span else None
        # Parse timestamp into a datetime object for sorting
        updated_dt = parse_timestamp(title_attr)
        # Format the datetime object into ISO format string for the XML element
        ET.SubElement(entry, "updated").text = updated_dt.isoformat()

        # Get model sizes as categories
        sizes = model.find_all("span", attrs={"x-test-size": True})
        for size in sizes:
            ET.SubElement(entry, "category", term=size.text.strip())

        # Get capabilities as categories
        capabilities = model.find_all("span", attrs={"x-test-capability": True})
        for capability in capabilities:
            ET.SubElement(entry, "category", term=capability.text.strip())

        # Additional stats in content
        pull_count = model.find("span", attrs={"x-test-pull-count": True})
        tag_count = model.find("span", attrs={"x-test-tag-count": True})

        # Include the summary at the top of the content
        content = f"<p>{description}</p>" if description else ""
        content += f"<p>Pulls: {pull_count.text if pull_count else 'N/A'}</p>"
        content += f"<p>Tags: {tag_count.text if tag_count else 'N/A'}</p>"

        ET.SubElement(entry, "content", type="html").text = content

        # Store the datetime object and the entry element for sorting
        entries_data.append((updated_dt, entry))

    return feed, entries_data


def save_atom_feed(filename, base_feed_element, entries_data):
    """
    Adds entries to a copy of the base feed element, serializes,
    and saves the Atom feed to a file.

    Args:
        filename (str): The path to save the file.
        base_feed_element (ET.Element): The basic <feed> structure.
        entries_data (list): A list of (datetime_obj, entry_element) tuples.
                             Assumed to be sorted if order matters.
    """
    # Create a deep copy to avoid modifying the original base element
    feed_copy = copy.deepcopy(base_feed_element)

    # Add entry elements to the copied feed
    for _, entry_element in entries_data:
        feed_copy.append(entry_element)

    # Convert ElementTree element to bytes, then parse with lxml for pretty printing
    xml_string_bytes = ET.tostring(feed_copy, encoding="utf-8")
    parser = etree.XMLParser(remove_blank_text=True)
    try:
        root = etree.fromstring(xml_string_bytes, parser)
        pretty_xml_string = etree.tostring(root, encoding="unicode", pretty_print=True)
    except Exception as e:
        print(f"Error pretty-printing XML for {filename}: {e}", file=sys.stderr)
        # Fallback to non-pretty printing if lxml fails
        pretty_xml_string = xml_string_bytes.decode('utf-8')


    # Write the output to the specified file
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(pretty_xml_string)
        print(f"Successfully saved feed to {filename}")
    except IOError as e:
        print(f"Error writing file {filename}: {e}", file=sys.stderr)


@click.command()
@click.argument("url")
def html_to_atom(url):
    """
    Fetches HTML from a URL, converts it to an Atom feed,
    and saves two files: 'atom.xml' (all items) and
    'atom-recent-20.xml' (most recent 20 items).

    URL: The web page URL (or file://path/to/file.html) to convert.
    """
    output_full_filename = "atom.xml"
    output_recent_filename = "atom-recent-20.xml"

    try:
        # Determine if URL is a local file path
        if url.startswith("file://"):
            filepath = url[7:]
            # Ensure file exists
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Local file not found: {filepath}")
            with open(filepath, "r", encoding="utf-8") as f:
                html_content = f.read()
            # Use file path directory as base for relative links if needed, though ollama.com uses absolute
            base_url = os.path.dirname(filepath) # Or maybe keep the original url? Let's stick to url for id
        else:
            # Fetch the HTML content via HTTP/S
            headers = {'User-Agent': 'AtomFeedGenerator/1.0'} # Be a good citizen
            response = requests.get(url, headers=headers, timeout=30) # Add timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            html_content = response.text
            base_url = url # Use the fetched URL as the base

        # Parse the HTML
        soup = BeautifulSoup(html_content, "lxml") # Use lxml parser

        # Create the base feed structure and extract entries with timestamps
        base_feed_element, entries_data = create_base_feed_and_entries(soup, base_url)

        # Sort entries by updated timestamp, most recent first
        entries_data.sort(key=lambda item: item[0], reverse=True)

        # --- Save the full feed ---
        save_atom_feed(output_full_filename, base_feed_element, entries_data)

        # --- Save the recent feed (top 20) ---
        recent_entries_data = entries_data[:20]
        save_atom_feed(output_recent_filename, base_feed_element, recent_entries_data)

    except requests.exceptions.RequestException as e:
        click.echo(f"Error fetching URL {url}: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"Error accessing file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        # Catch other potential errors (parsing, file writing, etc.)
        click.echo(f"An unexpected error occurred: {e}", err=True)
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        sys.exit(1)


if __name__ == "__main__":
    html_to_atom()

