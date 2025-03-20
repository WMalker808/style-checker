#!/Users/max_walker/wayback/bin/python3
import requests
from bs4 import BeautifulSoup
import difflib
import argparse
import re
from urllib.parse import urlparse
import datetime
import os
from flask import Flask, render_template, request, jsonify

# Create Flask app
app = Flask(__name__)

def get_wayback_url(original_url, timestamp=None):
    """
    Constructs a Wayback Machine URL for the given URL and optional timestamp.
    If no timestamp is provided, it will fetch the most recent snapshot.
    """
    # Parse the original URL
    parsed_url = urlparse(original_url)
    if not parsed_url.scheme:
        original_url = 'http://' + original_url
    
    if timestamp is None:
        # Get available snapshots
        availability_url = f"https://archive.org/wayback/available?url={original_url}"
        response = requests.get(availability_url)
        data = response.json()
        
        if 'archived_snapshots' in data and 'closest' in data['archived_snapshots']:
            return data['archived_snapshots']['closest']['url']
        else:
            return None
    else:
        # Format timestamp if needed
        if isinstance(timestamp, datetime.datetime):
            timestamp = timestamp.strftime("%Y%m%d%H%M%S")
        
        return f"https://web.archive.org/web/{timestamp}/{original_url}"

def fetch_page_content(url):
    """
    Fetches the content of a URL and returns the text.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

def extract_meaningful_text(html_content):
    """
    Extracts meaningful text content from HTML, ignoring styling and layout.
    Returns a list of (tag_type, text_content) tuples for significant text blocks.
    """
    if html_content is None:
        return []
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script, style tags, and other non-content elements
    for tag in soup(['script', 'style', 'meta', 'link', 'svg', 'path', 'noscript']):
        tag.decompose()
    
    # Extract meaningful content from specific tags
    significant_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'th', 'td', 'figcaption', 'blockquote']
    content_items = []
    
    for tag_name in significant_tags:
        for tag in soup.find_all(tag_name):
            # Skip empty or nearly empty tags
            text = tag.get_text().strip()
            # Filter out very short content or content that's just numbers/special chars
            if len(text) > 10 and not re.match(r'^[\d\W]+$', text):
                content_items.append((tag_name, text))
    
    return content_items

def find_significant_changes(old_items, new_items, similarity_threshold=0.7):
    """
    Compare two lists of content items and identify significant additions, removals, and modifications.
    Uses text similarity to determine if content has changed.
    Returns a dictionary with categorized changes.
    """
    results = {
        'added': [],
        'removed': [],
        'modified': []
    }
    
    # Find added and modified content
    for new_tag, new_text in new_items:
        best_match = None
        best_similarity = 0
        
        for old_tag, old_text in old_items:
            # Calculate similarity ratio
            similarity = difflib.SequenceMatcher(None, new_text, old_text).ratio()
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = (old_tag, old_text)
        
        # If no good match found, it's a new item
        if best_similarity < similarity_threshold:
            results['added'].append(f"<strong>{new_tag.upper()}</strong>: {new_text[:150]}..." if len(new_text) > 150 else f"<strong>{new_tag.upper()}</strong>: {new_text}")
        # If a similar but not identical match, it's a modification
        elif best_similarity < 0.95:
            results['modified'].append({
                'old': f"<strong>{best_match[0].upper()}</strong>: {best_match[1][:150]}..." if len(best_match[1]) > 150 else f"<strong>{best_match[0].upper()}</strong>: {best_match[1]}",
                'new': f"<strong>{new_tag.upper()}</strong>: {new_text[:150]}..." if len(new_text) > 150 else f"<strong>{new_tag.upper()}</strong>: {new_text}"
            })
    
    # Find removed content
    for old_tag, old_text in old_items:
        best_similarity = 0
        
        for new_tag, new_text in new_items:
            similarity = difflib.SequenceMatcher(None, old_text, new_text).ratio()
            best_similarity = max(best_similarity, similarity)
        
        if best_similarity < similarity_threshold:
            results['removed'].append(f"<strong>{old_tag.upper()}</strong>: {old_text[:150]}..." if len(old_text) > 150 else f"<strong>{old_tag.upper()}</strong>: {old_text}")
    
    return results

def compare_pages(old_content, new_content):
    """
    Compares two HTML pages and identifies significant text changes.
    Returns a dictionary of changes and HTML report.
    """
    if old_content is None or new_content is None:
        return None, "Could not compare pages due to fetch error."
    
    # Extract meaningful text from both documents
    old_items = extract_meaningful_text(old_content)
    new_items = extract_meaningful_text(new_content)
    
    # Find significant changes
    changes = find_significant_changes(old_items, new_items)
    
    # Generate HTML report
    html_report = """
    <div class="comparison-report">
        <style>
            .comparison-report { font-family: Arial, sans-serif; line-height: 1.6; }
            .changes-container { margin: 20px 0; }
            .change-card { margin-bottom: 20px; border: 1px solid #ddd; border-radius: 5px; overflow: hidden; }
            .card-header { padding: 10px 15px; font-weight: bold; color: white; }
            .added-header { background-color: #28a745; }
            .removed-header { background-color: #dc3545; }
            .modified-header { background-color: #fd7e14; }
            .card-body { padding: 15px; max-height: 400px; overflow-y: auto; }
            .change-item { padding: 10px; margin-bottom: 10px; border-radius: 4px; }
            .added-item { background-color: #e6ffed; border-left: 4px solid #28a745; }
            .removed-item { background-color: #ffeef0; border-left: 4px solid #dc3545; }
            .modified-item { background-color: #fff8e1; border-left: 4px solid #fd7e14; }
            .change-diff { display: flex; flex-direction: column; gap: 10px; }
            .old-text, .new-text { padding: 8px; border-radius: 4px; }
            .old-text { background-color: #ffeef0; }
            .new-text { background-color: #e6ffed; }
            .empty-message { color: #6c757d; font-style: italic; text-align: center; margin: 20px 0; }
        </style>
        
        <div class="changes-container">
            <div class="change-card">
                <div class="card-header added-header">New Content (%d)</div>
                <div class="card-body">
                    %s
                </div>
            </div>
            
            <div class="change-card">
                <div class="card-header removed-header">Removed Content (%d)</div>
                <div class="card-body">
                    %s
                </div>
            </div>
            
            <div class="change-card">
                <div class="card-header modified-header">Modified Content (%d)</div>
                <div class="card-body">
                    %s
                </div>
            </div>
        </div>
    </div>
    """ % (
        len(changes['added']),
        ''.join(f'<div class="change-item added-item">{item}</div>' for item in changes['added']) if changes['added'] else '<div class="empty-message">No new content detected</div>',
        len(changes['removed']),
        ''.join(f'<div class="change-item removed-item">{item}</div>' for item in changes['removed']) if changes['removed'] else '<div class="empty-message">No removed content detected</div>',
        len(changes['modified']),
        ''.join(f'<div class="change-item modified-item"><div class="change-diff"><div class="old-text">Before: {change["old"]}</div><div class="new-text">After: {change["new"]}</div></div></div>' for change in changes['modified']) if changes['modified'] else '<div class="empty-message">No modified content detected</div>'
    )
    
    return changes, html_report

def save_to_file(content, output_file=None):
    """
    Saves content to a file or returns it as a string.
    """
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Results saved to {output_file}"
    else:
        return content

def main(url, timestamp=None, output_file=None):
    """
    Main function to compare a URL between Wayback Machine and current live version.
    """
    # Get Wayback Machine URL
    wayback_url = get_wayback_url(url, timestamp)
    if not wayback_url:
        return "No Wayback Machine snapshot found for this URL."
    
    print(f"Using Wayback Machine URL: {wayback_url}")
    
    # Fetch content
    wayback_content = fetch_page_content(wayback_url)
    current_content = fetch_page_content(url)
    
    if wayback_content is None:
        return "Could not fetch Wayback Machine content."
    
    if current_content is None:
        return "Could not fetch current live content."
    
    # Compare pages
    changes, html_report = compare_pages(wayback_content, current_content)
    
    # Create a simple HTML page with the report
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Website Text Changes</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        </style>
    </head>
    <body>
        <h1>Text Content Changes</h1>
        <p><strong>Wayback URL:</strong> <a href="{wayback_url}" target="_blank">{wayback_url}</a></p>
        <p><strong>Current URL:</strong> <a href="{url}" target="_blank">{url}</a></p>
        
        {html_report}
    </body>
    </html>
    """
    
    # Save or return results
    return save_to_file(full_html, output_file)

# Flask routes
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Wayback Machine Comparison Tool</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; line-height: 1.6; color: #333; }
            .container { max-width: 800px; margin: 0 auto; padding: 20px; }
            header { background-color: #f8f9fa; padding: 20px 0; border-bottom: 1px solid #ddd; margin-bottom: 30px; }
            h1 { margin: 0; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input[type="text"], input[type="date"] { width: 100%; padding: 10px; box-sizing: border-box; border: 1px solid #ddd; border-radius: 4px; }
            button { background-color: #0366d6; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
            button:hover { background-color: #0353b0; }
            .info { background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-top: 30px; }
            .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 14px; }
        </style>
    </head>
    <body>
        <header>
            <div class="container">
                <h1>Wayback Machine Comparison Tool</h1>
            </div>
        </header>
        
        <div class="container">
            <form action="/compare" method="post">
                <div class="form-group">
                    <label for="url">URL to Compare:</label>
                    <input type="text" id="url" name="url" placeholder="Enter URL (e.g., example.com)" required>
                </div>
                <div class="form-group">
                    <label for="date">Wayback Machine Date (optional):</label>
                    <input type="date" id="date" name="date">
                </div>
                <button type="submit">Compare Pages</button>
            </form>
            
            <div class="info">
                <h3>About This Tool</h3>
                <p>This tool compares a webpage from the Wayback Machine archive with its current live version, focusing only on significant text changes. It ignores layout, styling, and minor differences to show you what truly matters.</p>
                <p>Simply enter a URL and optionally select a date to see how the content has changed over time.</p>
            </div>
            
            <div class="footer">
                <p>This tool uses the Wayback Machine API from the Internet Archive to access historical versions of webpages.</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/compare', methods=['POST'])
def compare():
    url = request.form.get('url')
    date_str = request.form.get('date')
    
    timestamp = None
    if date_str:
        try:
            date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            timestamp = date_obj.strftime("%Y%m%d")
        except ValueError:
            return "Invalid date format"
    
    # Get Wayback Machine URL
    wayback_url = get_wayback_url(url, timestamp)
    if not wayback_url:
        return "No Wayback Machine snapshot found for this URL."
    
    # Fetch content
    wayback_content = fetch_page_content(wayback_url)
    current_content = fetch_page_content(url)
    
    if wayback_content is None:
        return "Could not fetch Wayback Machine content."
    
    if current_content is None:
        return "Could not fetch current live content."
    
    # Compare pages
    changes, html_report = compare_pages(wayback_content, current_content)
    
    # Create a simple HTML page with the report
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Website Text Changes</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; line-height: 1.6; color: #333; }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
            header {{ background-color: #f8f9fa; padding: 20px 0; border-bottom: 1px solid #ddd; margin-bottom: 30px; }}
            h1 {{ margin: 0; }}
            .back-link {{ display: inline-block; margin-bottom: 20px; color: #0366d6; text-decoration: none; }}
            .back-link:hover {{ text-decoration: underline; }}
            .info-panel {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 30px; }}
            .url-display {{ display: block; margin: 10px 0; padding: 10px; background-color: #f1f8ff; border-radius: 4px; }}
            .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 14px; }}
        </style>
    </head>
    <body>
        <header>
            <div class="container">
                <h1>Website Text Changes</h1>
            </div>
        </header>
        
        <div class="container">
            <a href="/" class="back-link">← Back to Search</a>
            
            <div class="info-panel">
                <h2>Comparison Details</h2>
                <div class="url-display">
                    <strong>Archive Version:</strong> <a href="{wayback_url}" target="_blank">{wayback_url}</a>
                </div>
                <div class="url-display">
                    <strong>Current Version:</strong> <a href="{url}" target="_blank">{url}</a>
                </div>
                <p><strong>Note:</strong> This comparison focuses only on significant text content changes, ignoring layout, styling, and minor differences.</p>
            </div>
            
            {html_report}
            
            <div class="footer">
                <p>This tool uses the Wayback Machine API from the Internet Archive to access historical versions of webpages.</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/api/compare', methods=['POST'])
def api_compare():
    """
    API endpoint for programmatic comparison.
    """
    data = request.json
    
    if not data or 'url' not in data:
        return jsonify({"error": "URL is required"}), 400
    
    url = data['url']
    timestamp = data.get('timestamp')
    
    # Get Wayback Machine URL
    wayback_url = get_wayback_url(url, timestamp)
    if not wayback_url:
        return jsonify({"error": "No Wayback Machine snapshot found for this URL."}), 404
    
    # Fetch content
    wayback_content = fetch_page_content(wayback_url)
    current_content = fetch_page_content(url)
    
    if wayback_content is None:
        return jsonify({"error": "Could not fetch Wayback Machine content."}), 500
    
    if current_content is None:
        return jsonify({"error": "Could not fetch current live content."}), 500
    
    # Compare structure only for API
    changes, _ = compare_pages(wayback_content, current_content)
    
    # Return results
    return jsonify({
        "wayback_url": wayback_url,
        "live_url": url,
        "changes": changes
    })

if __name__ == "__main__":
    # Command-line interface
    parser = argparse.ArgumentParser(description='Compare a URL between Wayback Machine and current live version.')
    parser.add_argument('--url', help='URL to compare')
    parser.add_argument('--timestamp', '-t', help='Wayback Machine timestamp (YYYYMMDD or YYYYMMDDHHMMSS)')
    parser.add_argument('--output', '-o', help='Output file for diff')
    parser.add_argument('--web', '-w', action='store_true', help='Run as web application')
    parser.add_argument('--port', '-p', type=int, default=5000, help='Port for web application')
    
    args = parser.parse_args()
    
    if args.web:
        # Run as web application
        print(f"Starting web application on port {args.port}...")
        app.run(debug=True, port=args.port)
    else:
        # Run as command-line tool
        if not args.url:
            parser.error("the --url argument is required when not using --web")
        result = main(args.url, args.timestamp, args.output)
        print(result)