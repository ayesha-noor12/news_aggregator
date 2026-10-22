import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

def get_robots_txt(base_url):
    robots_url = urljoin(base_url, '/robots.txt')
    try:
        response = requests.get(robots_url)
        if response.status_code == 200:
            print(f"\n📄 robots.txt found at {robots_url}")
            print("-" * 50)
            print(response.text)
        else:
            print(f"⚠️ robots.txt not found at {robots_url}")
    except Exception as e:
        print(f"❌ Error fetching robots.txt: {e}")

def find_privacy_policy_links(base_url):
    try:
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=True)
        found = False

        print(f"\n🔍 Scanning {base_url} for privacy/terms links:")
        for link in links:
            text = link.get_text(strip=True).lower()
            href = link['href'].lower()
            if "privacy" in text or "privacy" in href or "terms" in text or "terms" in href:
                full_url = urljoin(base_url, link['href'])
                print(f"✅ Found: {text} → {full_url}")
                found = True
        if not found:
            print("❌ No privacy or terms link found on homepage.")
    except Exception as e:
        print(f"❌ Error fetching homepage: {e}")

if __name__ == "__main__":
    website = input("🔗 Enter website URL (e.g., https://example.com): ").strip()
    if not website.startswith("http"):
        website = "https://" + website

    get_robots_txt(website)
    find_privacy_policy_links(website)
