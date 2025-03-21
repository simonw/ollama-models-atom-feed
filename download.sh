#!/usr/bin/env bash
#
# download - Simple downloader that always constructs the filename from the URL
# Usage: ./download.sh URL

set -e

# Function to detect MIME type and return appropriate extension
get_file_extension() {
  local file_path="$1"
  local mime_type=$(file --mime-type -b "$file_path")
  local extension=""
  
  case "$mime_type" in
    text/html)                extension=".html" ;;
    application/json)         extension=".json" ;;
    text/plain)               extension=".txt" ;;
    application/javascript)   extension=".js" ;;
    application/xml|text/xml) extension=".xml" ;;
    application/pdf)          extension=".pdf" ;;
    image/jpeg)               extension=".jpg" ;;
    image/png)                extension=".png" ;;
    image/gif)                extension=".gif" ;;
    image/svg+xml)            extension=".svg" ;;
    application/zip)          extension=".zip" ;;
    application/gzip)         extension=".gz" ;;
    application/x-tar)        extension=".tar" ;;
    application/x-bzip2)      extension=".bz2" ;;
    *)                        extension=".html" ;; # Default to HTML if unknown
  esac
  
  echo "$extension"
}

# Check if URL provided
if [ $# -ne 1 ]; then
  echo "Usage: $0 URL"
  exit 1
fi

URL="$1"

# Validate URL format (must start with http:// or https://)
if [[ ! "$URL" =~ ^https?:// ]]; then
  echo "Error: URL must start with http:// or https://"
  exit 1
fi

# Create temporary file
TEMP_FILE=$(mktemp)

# Download the file
echo "Downloading $URL"
curl -s -L "$URL" -o "$TEMP_FILE" || {
  echo "Error: Failed to download $URL"
  rm -f "$TEMP_FILE"
  exit 1
}

# Get file extension based on MIME type
EXTENSION=$(get_file_extension "$TEMP_FILE")

# Always construct filename from the URL, replacing slashes with hyphens
FILENAME=$(echo "$URL" | sed -E 's|^https?://||' | sed -E 's|^www\.||' | sed 's|/$||' | sed 's|/|-|g')

# Add extension to the filename
FILENAME="${FILENAME}${EXTENSION}"

# Make sure we don't end up with just an extension
if [ "$FILENAME" = "${EXTENSION}" ]; then
  FILENAME="index${EXTENSION}"
fi

# Get the current directory to ensure we save to this location
CURRENT_DIR="$(pwd)"
FULL_PATH="${CURRENT_DIR}/${FILENAME}"

# Pretty-print JSON if applicable
if [ "$EXTENSION" = ".json" ]; then
  # Create another temporary file for the pretty-printed version
  PRETTY_TEMP=$(mktemp)
  # Try to pretty-print with jq, but don't fail if jq fails
  if command -v jq &> /dev/null; then
    if jq . "$TEMP_FILE" > "$PRETTY_TEMP" 2>/dev/null; then
      mv "$PRETTY_TEMP" "$TEMP_FILE"
    else
      rm -f "$PRETTY_TEMP"
    fi
  else
    rm -f "$PRETTY_TEMP"
  fi
fi

# Move to final destination
mv "$TEMP_FILE" "$FULL_PATH"
