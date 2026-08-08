import requests
import json

# Try downloading GNT from a different source
def download_gnt_from_fcbh():
    """Download from Faith Comes By Hearing API"""
    # FCBH API requires registration
    # This is just an example
    pass

def download_gnt_from_ebible():
    """Download from eBible API"""
    # eBible API
    url = "https://ebible.org/api/api.php"
    params = {
        'book': 'GEN',
        'chapter': '1',
        'version': 'eng-GNT'
    }
    # This may not work, but worth a try
    pass

def download_gnt_from_web():
    """Download from web sources"""
    # Try various web sources
    urls = [
        "https://www.gutenberg.org/files/",
        "https://www.o-bible.com/gnt/",
        "https://www.biblegateway.com/versions/Good-News-Translation-GNT-Bible/",
    ]
    print("📚 Possible sources for GNT:")
    for url in urls:
        print(f"  - {url}")

if __name__ == "__main__":
    download_gnt_from_web()
