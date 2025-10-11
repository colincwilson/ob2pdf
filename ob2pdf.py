import xml.etree.ElementTree as ET
import json
import re
import sys
import os
import unicodedata
from pypdf import PdfReader, PdfWriter
from pathlib import Path

# --- 1. CORE UTILITY FUNCTIONS ---

def sanitize_title(title):
    """
    Converts title to ASCII-safe characters, 
    removes control characters, and cleans up common JSON/PDF breaking characters.
    """
    if title is None:
        return ""
    
    title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('utf-8')
    title = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', title)
    title = title.replace('"', '').replace('\\', '')
    title = title.replace('–', '-').replace('—', '--')
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def find_pdf_by_hash(start_dir, unique_key):
    """
    Uses glob to robustly find the PDF file in the specified directory by its unique hash.
    Returns the absolute Path object of the found PDF.
    """
    search_pattern = f"*{unique_key}*.pdf"
    pdf_files = list(Path(start_dir).glob(search_pattern))
    
    if not pdf_files:
        return None
    
    return pdf_files[0].resolve()

def extract_bookmarks(xml_path, pdf_path_obj):
    """
    Extracts and sanitizes bookmarks for the target PDF, using the hash found in its filename.
    Returns (bookmarks_list, unique_key)
    """
    XBEL_NS = 'http://www.w3.org/2002/xbel'
    NAMESPACES = {'xbel': XBEL_NS}

    if not Path(xml_path).exists():
        print(f"Error: Bookmarks file not found at: {xml_path}")
        return None, None
        
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error: Could not parse bookmarks.xml. {e}")
        return None, None

    # --- AUTOMATIC HASH DETERMINATION ---
    pdf_filename = pdf_path_obj.name
    match_key_search = re.search(r'-- ([0-9a-f]{32}) --', pdf_filename)
    
    if not match_key_search:
         print("Error: Could not extract the 32-character hash from the PDF filename.")
         return None, None
         
    unique_key = match_key_search.group(1)

    cpdf_bookmarks = []
    page_regex = re.compile(r'#(\d+)') 

    for bookmark in root.iter('bookmark'):
        href = bookmark.get('href')
        
        if href and unique_key in href:
            title_tag = bookmark.find('title')
            
            if title_tag is None:
                title_tag = bookmark.find('xbel:title', NAMESPACES)
            
            if title_tag is None or not title_tag.text:
                continue
                
            match = page_regex.search(href)
            
            if match:
                okular_page = int(match.group(1))
                cpdf_page = okular_page + 1 

                cpdf_bookmarks.append({
                    "Title": sanitize_title(title_tag.text),
                    "Page": cpdf_page,
                    "Level": 1
                })

    if not cpdf_bookmarks:
        print(f"Error: Found no bookmarks for the PDF using key '{unique_key}' in bookmarks.xml.")
        return None, None

    cpdf_bookmarks.sort(key=lambda x: x['Page'])
    
    return cpdf_bookmarks, unique_key

def inject_bookmarks_pypdf(pdf_path_str, bookmarks, output_path):
    """
    Injects the sorted bookmarks into the PDF using pypdf.
    """
    try:
        reader = PdfReader(pdf_path_str)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        for mark in bookmarks:
            page_index = mark['Page'] - 1 

            writer.add_outline_item(
                mark['Title'], 
                page_index
            )

        with open(output_path, 'wb') as f:
            writer.write(f)
            
        # FINAL SUCCESS MESSAGE WITH BLANK LINES
        num_bookmarks = len(bookmarks)
        print(f"\nSuccess! {num_bookmarks} bookmarks injected into: {output_path.name}\n")

    except Exception as e:
        print(f"Error during PDF processing with pypdf: {e}")
        print("\nHint: If the PDF is heavily structured or encrypted, try cleaning it first with Ghostscript (gs -dBATCH -dNOPAUSE -q -sDEVICE=pdfwrite -sOutputFile=clean_input.pdf INPUT.pdf)")
        sys.exit(1)

# --- 2. MAIN EXECUTION ---

def find_xml_path_auto(pdf_path_obj):
    """
    Attempts to locate the bookmarks.xml file in preferred locations.
    """
    xml_filename = 'bookmarks.xml'
    
    # 1. Default Okular (Flatpak) location
    default_okular_path = Path.home() / f'.var/app/org.kde.okular/data/okular/{xml_filename}'
    
    # 2. Current Working Directory (CWD)
    cwd_path = Path.cwd() / xml_filename
    
    # 3. PDF's Directory
    pdf_dir_path = pdf_path_obj.parent / xml_filename
    
    search_paths = [
        ("Default Okular Path", default_okular_path),
        ("Current Working Directory", cwd_path),
        ("PDF's Directory", pdf_dir_path)
    ]
    
    for label, path in search_paths:
        if path.exists():
            return path.as_posix()

    # If not found, report all locations checked (only happens if auto-mode fails and exits later)
    print("\nBookmarks file was not found automatically.")
    print("Checked locations:")
    for label, path in search_paths:
         print(f"  - {label}: {path.as_posix()}")
         
    return None

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("\nERROR: Invalid number of arguments.")
        print("Auto Mode: python3 ob2pdf.py <pdf_file_path>")
        print("Manual Mode: python3 ob2pdf.py <pdf_file_path> <bookmarks_xml_path>")
        sys.exit(1)
        
    input_pdf_path = sys.argv[1]
    
    # Resolve PDF Path (Crucial for directory lookup)
    try:
        temp_pdf_path_obj = Path(input_pdf_path).resolve()
    except Exception:
        print(f"ERROR: Could not process the input PDF path string: {input_pdf_path}")
        sys.exit(1)

    # --- Determine XML Path ---
    if len(sys.argv) == 3:
        # Manual Mode: XML path was provided
        xml_path = sys.argv[2]
        
    else:
        # Auto Mode: Attempt to find XML automatically
        xml_path = find_xml_path_auto(temp_pdf_path_obj)
        
        if xml_path is None:
            # If auto-discovery fails, prompt the user with clear instructions
            print("\nERROR: Bookmarks file (bookmarks.xml) was not found in any standard location.")
            print("Please run the script in Manual Mode and specify the path to your bookmarks file:")
            print(f"Example: python3 ob2pdf.py \"{input_pdf_path}\" /path/to/your/bookmarks.xml")
            sys.exit(1)
        
    # --- Check PDF Existence ---
    if not temp_pdf_path_obj.exists():
        print(f"Error: Input PDF file does not exist or path is invalid: {input_pdf_path}")
        print("Please check for problematic characters in the path or use the full absolute path.")
        sys.exit(1)


    # --- Step A: Automatic Hash Determination, Extraction and Sorting ---
    bookmarks, unique_key = extract_bookmarks(xml_path, temp_pdf_path_obj)
    if bookmarks is None:
        sys.exit(1)

    # --- Step B: ROBUST FILE LOCATION using GLOB ---
    pdf_path_obj = find_pdf_by_hash(temp_pdf_path_obj.parent, unique_key)
    
    if pdf_path_obj is None:
        print(f"ERROR: File exists, but could not be located by hash search in directory {temp_pdf_path_obj.parent}")
        print("Please manually rename the PDF to use only standard ASCII characters (e.g., replace non-standard quotes with standard ones) and try again.")
        sys.exit(1)
        
    pdf_path_str = pdf_path_obj.as_posix()

    # --- Step C: Define Output Paths (File-Length Safe) ---
    pdf_directory = pdf_path_obj.parent
    
    json_filename = f"{unique_key}_temp.json"
    json_path = pdf_directory / json_filename
    
    output_filename = pdf_path_obj.stem + "_bookmarked.pdf"
    output_path = pdf_directory / output_filename
    
    # --- Step D: Save Intermediate JSON (Temporary) ---
    try:
        with open(json_path, 'w') as f:
            json.dump(bookmarks, f, indent=2)
    except Exception as e:
        print(f"CRITICAL ERROR WRITING JSON: {e}") 
        sys.exit(1)

    # --- Step E: Injection (Prints SUCCESS) ---
    inject_bookmarks_pypdf(pdf_path_str, bookmarks, output_path)

    # --- Step F: Cleanup ---
    try:
        os.remove(json_path)
    except Exception as e:
        print(f"Warning: Could not delete temporary JSON file: {e}")

if __name__ == '__main__':
    main()
