import sys
import click
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from lxml import etree


def parse_timestamp(title_attr):
    """Parse timestamp from title attribute in the format 'Mar 13, 2025 12:39 PM UTC'."""
    if not title_attr:
        return datetime.now().isoformat()

    try:
        dt = datetime.strptime(title_attr, "%b %d, %Y %I:%M %p %Z")
        return dt.isoformat()
    except ValueError:
        # Default to current time if unable to parse
        return datetime.now().isoformat()


def create_atom_feed(soup, base_url):
    """Create an Atom feed from the parsed HTML."""
    # Create the root element
    feed = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")

    # Add feed metadata
    ET.SubElement(feed, "title").text = "Ollama models"
    ET.SubElement(feed, "id").text = base_url
    author = ET.SubElement(feed, "author")
    ET.SubElement(author, "name").text = "Model Library"
    ET.SubElement(feed, "link", href=base_url, rel="self")

    # Find all model items
    models = soup.find_all("li", attrs={"x-test-model": True})

    for model in models:
        entry = ET.SubElement(feed, "entry")

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
        description = (
            model.find("p", class_="max-w-lg").text.strip()
            if model.find("p", class_="max-w-lg")
            else ""
        )
        ET.SubElement(entry, "summary").text = description

        # Get updated time from the title attribute
        date_span = model.find("span", class_="flex items-center", title=True)
        title_attr = date_span.get("title") if date_span else None
        updated_iso = parse_timestamp(title_attr)
        ET.SubElement(entry, "updated").text = updated_iso

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
        content = f"<p>{description}</p>"
        content += f"<p>Pulls: {pull_count.text if pull_count else 'N/A'}</p>"
        content += f"<p>Tags: {tag_count.text if tag_count else 'N/A'}</p>"

        ET.SubElement(entry, "content", type="html").text = content

    # Convert to ElementTree element, then to lxml element for pretty printing
    xml_string = ET.tostring(feed, encoding="utf-8")
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(xml_string, parser)
    return etree.tostring(root, encoding="unicode", pretty_print=True)


@click.command()
@click.argument("url")
@click.option(
    "--output",
    "-o",
    type=click.File("w"),
    default="-",
    help="Output file path. Defaults to stdout.",
)
def html_to_atom(url, output):
    """
    Convert HTML from the given URL to an Atom feed.

    URL: The web page URL to convert to Atom
    """
    try:
        # If URL is actually a file path, read locally
        if url.startswith("file://"):
            with open(url[7:], "r") as f:
                html_content = f.read()
        else:
            # Fetch the HTML content
            response = requests.get(url)
            response.raise_for_status()
            html_content = response.text

        # Parse the HTML
        soup = BeautifulSoup(html_content, "lxml")

        # Create the atom feed
        atom_feed = create_atom_feed(soup, url)

        # Write the output
        output.write('<?xml version="1.0" encoding="utf-8"?>\n')
        output.write(atom_feed)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    html_to_atom()
