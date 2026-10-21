import os
from dotenv import load_dotenv
load_dotenv()


import sys
import re
import feedparser # type: ignore
import hashlib
import mysql.connector # type: ignore
from datetime import datetime
from bs4 import BeautifulSoup   # pip install beautifulsoup4
import http.client
import socket
import urllib.error

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)
cursor = db.cursor()

# --- Utility: clean and validate content ---
def clean_text(text):
    """Remove HTML tags and extra whitespace from text."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)

def is_valid_content(text):
    """Check if content is non-empty and not just HTML/junk."""
    if not text:
        return False
    cleaned = clean_text(text)
    if not cleaned or cleaned.isspace():
        return False
    # If cleaned text is just like "AFP", "Reuters" etc., you can filter further
    if len(cleaned) < 20:  # Too short → skip
        return False
    return True

# --- Utility functions for DB ---
def get_or_create_source(source):
    cursor.execute("SELECT id FROM news_sources WHERE name = %s", (source['name'],))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute(
        "INSERT INTO news_sources (name, url, country, bias, trust_score) VALUES (%s, %s, %s, %s, %s)",
        (source['name'], source['url'], source['country'], source['bias'], source['trust_score'])
    )
    db.commit()
    return cursor.lastrowid

def article_exists(hash_value):
    cursor.execute("SELECT id FROM news_articles WHERE hash = %s", (hash_value,))
    return cursor.fetchone() is not None

def get_or_create_topic_cluster(topic):
    cursor.execute("SELECT id FROM topic_clusters WHERE topic = %s", (topic,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute(
        "INSERT INTO topic_clusters (topic, summary, created_at) VALUES (%s, %s, %s)",
        (topic, '', datetime.now())
    )
    db.commit()
    return cursor.lastrowid

# --- RSS ingestion ---
rss_feeds = [
    
    {'name': 'Reuters', 'url': 'http://feeds.reuters.com/reuters/topNews', 'country': 'Global', 'bias': 'center', 'trust_score': 4.5},
    {'name': 'Associated Press (AP)', 'url': 'https://apnews.com/rss', 'country': 'USA', 'bias': 'center', 'trust_score': 4.6},
    {'name': 'BBC News', 'url': 'http://feeds.bbci.co.uk/news/rss.xml', 'country': 'UK', 'bias': 'center-left', 'trust_score': 4.5},
    {'name': 'CNN', 'url': 'http://rss.cnn.com/rss/edition.rss', 'country': 'USA', 'bias': 'left', 'trust_score': 3.8},
    {'name': 'Al Jazeera', 'url': 'http://www.aljazeera.com/xml/rss/all.xml', 'country': 'Qatar', 'bias': 'center', 'trust_score': 4.1},
    {'name': 'The New York Times', 'url': 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml', 'country': 'USA', 'bias': 'left', 'trust_score': 4.2},
    {'name': 'The Washington Post', 'url': 'http://feeds.washingtonpost.com/rss/world', 'country': 'USA', 'bias': 'left', 'trust_score': 4.2},
    {'name': 'The Guardian', 'url': 'https://www.theguardian.com/world/rss', 'country': 'UK', 'bias': 'left', 'trust_score': 4.3},
    {'name': 'Financial Times', 'url': 'https://www.ft.com/?format=rss', 'country': 'UK', 'bias': 'center-right', 'trust_score': 4.3},
    {'name': 'Bloomberg', 'url': 'https://www.bloomberg.com/feed/podcast/etf-report.xml', 'country': 'USA', 'bias': 'center', 'trust_score': 4.4},
    {'name': 'MSNBC', 'url': 'http://www.msnbc.com/feeds/latest', 'country': 'USA', 'bias': 'left', 'trust_score': 3.7},
    {'name': 'Fox News', 'url': 'http://feeds.foxnews.com/foxnews/latest', 'country': 'USA', 'bias': 'right', 'trust_score': 3.2},
    {'name': 'NPR', 'url': 'https://feeds.npr.org/1001/rss.xml', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.5},
    #{'name': 'PBS NewsHour', 'url': 'https://www.pbs.org/newshour/feeds/rss/headlines', 'country': 'USA', 'bias': 'center', 'trust_score': 4.4},
    #{'name': 'CBC News', 'url': 'https://www.cbc.ca/cmlink/rss-world', 'country': 'Canada', 'bias': 'center-left', 'trust_score': 4.4},
    {'name': 'ABC News (US)', 'url': 'https://abcnews.go.com/abcnews/topstories', 'country': 'USA', 'bias': 'center', 'trust_score': 4.0},
    {'name': 'CBS News', 'url': 'https://www.cbsnews.com/latest/rss/main', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.0},
    {'name': 'The Hill', 'url': 'https://thehill.com/rss/syndicator/19110', 'country': 'USA', 'bias': 'center-right', 'trust_score': 3.9},
    {'name': 'Politico', 'url': 'https://www.politico.com/rss/politics08.xml', 'country': 'USA', 'bias': 'center', 'trust_score': 4.1},
    {'name': 'Axios', 'url': 'https://www.axios.com/rss', 'country': 'USA', 'bias': 'center', 'trust_score': 4.0},
    {'name': 'Reuters World News', 'url': 'http://feeds.reuters.com/Reuters/worldNews', 'country': 'Global', 'bias': 'center', 'trust_score': 4.5},
    {'name': 'Reuters Technology News', 'url': 'http://feeds.reuters.com/reuters/technologyNews', 'country': 'Global', 'bias': 'center', 'trust_score': 4.3},
    {'name': 'Reuters Business News', 'url': 'http://feeds.reuters.com/reuters/businessNews', 'country': 'Global', 'bias': 'center-right', 'trust_score': 4.2},
    {'name': 'Reuters Science News', 'url': 'http://feeds.reuters.com/reuters/scienceNews', 'country': 'Global', 'bias': 'center-left', 'trust_score': 4.1},
    {'name': 'Reuters Health News', 'url': 'http://feeds.reuters.com/reuters/healthNews', 'country': 'Global', 'bias': 'center-left', 'trust_score': 4.0},
    {'name': 'The Guardian', 'url': 'https://www.theguardian.com/uk-news/rss', 'country': 'UK', 'bias': 'left', 'trust_score': 4.3},
    {'name': 'BBC News UK', 'url': 'http://feeds.bbci.co.uk/news/uk/rss.xml', 'country': 'UK', 'bias': 'center-left', 'trust_score': 4.5},
    {'name': 'The Telegraph', 'url': 'https://www.telegraph.co.uk/news/rss.xml', 'country': 'UK', 'bias': 'right', 'trust_score': 4.0},
    {'name': 'The Independent', 'url': 'https://www.independent.co.uk/news/uk/rss', 'country': 'UK', 'bias': 'center-left', 'trust_score': 4.1},
    {'name': 'Daily Mail', 'url': 'https://www.dailymail.co.uk/articles.rss', 'country': 'UK', 'bias': 'right', 'trust_score': 3.2},
    {'name': 'Daily Mirror', 'url': 'https://www.mirror.co.uk/news/uk-news/rss.xml', 'country': 'UK', 'bias': 'left', 'trust_score': 3.5},
    {'name': 'The Sun', 'url': 'https://www.thesun.co.uk/news/uknews/feed/', 'country': 'UK', 'bias': 'right', 'trust_score': 3.0},
    {'name': 'Sky News', 'url': 'https://feeds.skynews.com/feeds/rss/uk.xml', 'country': 'UK', 'bias': 'center-right', 'trust_score': 4.0},
    {'name': 'Financial Times (UK)', 'url': 'https://www.ft.com/?format=rss', 'country': 'UK', 'bias': 'center-right', 'trust_score': 4.3},
    {'name': 'ProPublica', 'url': 'https://www.propublica.org/feeds/all.xml', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.7},
    {'name': 'Center for Investigative Reporting (Reveal)', 'url': 'https://revealnews.org/feed/', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.5},
    {'name': 'The Marshall Project', 'url': 'https://www.themarshallproject.org/feeds/news.xml', 'country': 'USA', 'bias': 'center', 'trust_score': 4.6},
    {'name': 'ICIJ (International Consortium of Investigative Journalists)', 'url': 'https://www.icij.org/feed/', 'country': 'International', 'bias': 'center-left', 'trust_score': 4.8},
    {'name': 'Trustworthy News Network', 'url': '', 'country': 'USA', 'bias': 'center', 'trust_score': 4.0},  # RSS unavailable, may need scraping or verification
    {'name': 'Institute for Nonprofit News (INN)', 'url': 'https://inn.org/feed/', 'country': 'USA', 'bias': 'center', 'trust_score': 4.2},
    {'name': 'MarketWatch', 'url': 'https://www.marketwatch.com/rss/topstories', 'country': 'USA', 'bias': 'center-right', 'trust_score': 4.0},
    {'name': 'Bloomberg Politics', 'url': 'https://www.bloomberg.com/politics/feed', 'country': 'USA', 'bias': 'center-right', 'trust_score': 4.2},
    {'name': 'CNET', 'url': 'https://www.cnet.com/rss/news/', 'country': 'USA', 'bias': 'center', 'trust_score': 4.1},
    {'name': 'Wired', 'url': 'https://www.wired.com/feed/rss', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.3},
    {'name': 'Engadget', 'url': 'https://www.engadget.com/rss.xml', 'country': 'USA', 'bias': 'center', 'trust_score': 4.0},
    {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.3},
    {'name': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.2},
    {'name': 'Ars Technica', 'url': 'http://feeds.arstechnica.com/arstechnica/index', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.1},
    {'name': 'The Economist', 'url': 'https://www.economist.com/latest/rss.xml', 'country': 'UK', 'bias': 'center', 'trust_score': 4.6},
    {'name': 'Financial Times Alphaville', 'url': 'https://www.ft.com/stream/rss/topicsId/MTA0WnR4aU10RU9yd0YxVFhTZEc=', 'country': 'UK', 'bias': 'center', 'trust_score': 4.5},
    {'name': 'Dawn News', 'url': 'https://www.dawn.com/feeds/home', 'country': 'Pakistan', 'bias': 'center-left', 'trust_score': 4.3},
    {'name': 'Geo News', 'url': 'https://feeds.feedburner.com/geo/hegG', 'country': 'Pakistan', 'bias': 'center', 'trust_score': 4.1},
    {'name': 'ARY News', 'url': 'https://arynews.tv/en/feed/', 'country': 'Pakistan', 'bias': 'right', 'trust_score': 3.8},
    {'name': 'Dunya News', 'url': 'https://dunyanews.tv/en/rssfeed/index.rss', 'country': 'Pakistan', 'bias': 'center-right', 'trust_score': 3.9},
    {'name': 'Express Tribune', 'url': 'https://tribune.com.pk/feed', 'country': 'Pakistan', 'bias': 'center-left', 'trust_score': 4.0},
    {'name': 'The News International', 'url': 'https://www.thenews.com.pk/rss/1/1', 'country': 'Pakistan', 'bias': 'center', 'trust_score': 4.0},
    {'name': 'Samaa TV', 'url': 'https://www.samaa.tv/feed/', 'country': 'Pakistan', 'bias': 'center', 'trust_score': 3.8},
    {'name': '92 News', 'url': 'https://92newshd.tv/feed/', 'country': 'Pakistan', 'bias': 'right', 'trust_score': 3.6},
    {'name': 'Pakistan Today', 'url': 'https://www.pakistantoday.com.pk/feed/', 'country': 'Pakistan', 'bias': 'center-left', 'trust_score': 3.7},
    {'name': 'Business Recorder', 'url': 'https://www.brecorder.com/news/rss.xml', 'country': 'Pakistan', 'bias': 'center', 'trust_score': 4.1},
    {'name': 'Google News', 'url': 'https://news.google.com/rss', 'country': 'Global', 'bias': 'aggregated', 'trust_score': 4.6},
    #{'name': 'MSN News', 'url': 'https://www.msn.com/en-us/feed', 'country': 'USA', 'bias': 'aggregated', 'trust_score': 4.2},
    {'name': 'Yahoo News', 'url': 'https://www.yahoo.com/news/rss', 'country': 'USA', 'bias': 'aggregated', 'trust_score': 4.1},
    {'name': 'Reddit r/news', 'url': 'https://www.reddit.com/r/news/.rss', 'country': 'Global', 'bias': 'community-curated', 'trust_score': 3.9},
    {'name': 'Flipboard', 'url': 'https://flipboard.com/@flipboard/rss', 'country': 'Global', 'bias': 'aggregated', 'trust_score': 4.0},
    {'name': 'Feedly (Tech)', 'url': 'https://feedly.com/i/subscription/feed/http://feeds.arstechnica.com/arstechnica/index', 'country': 'Global', 'bias': 'aggregated', 'trust_score': 4.2},
    {'name': 'Pocket (Popular)', 'url': 'https://getpocket.com/explore/trending?src=home', 'country': 'Global', 'bias': 'aggregated', 'trust_score': 4.1},
    {'name': 'SmartNews', 'url': 'https://www.smartnews.com/en/feed', 'country': 'Global', 'bias': 'aggregated', 'trust_score': 4.0},
    {'name': 'Apple News', 'url': 'https://apple.news', 'country': 'Global', 'bias': 'aggregated', 'trust_score': 4.3},  # No public RSS feed
    {'name': 'Substack (General)', 'url': 'https://substack.com/discover', 'country': 'Global', 'bias': 'creator-driven', 'trust_score': 4.0},
    {'name': 'VICE', 'url': 'https://www.vice.com/en/rss', 'country': 'USA', 'bias': 'left', 'trust_score': 3.8},
    {'name': 'BuzzFeed News', 'url': 'https://www.buzzfeed.com/world.xml', 'country': 'USA', 'bias': 'left', 'trust_score': 3.6},
    {'name': 'Pitchfork', 'url': 'https://pitchfork.com/rss/news/', 'country': 'USA', 'bias': 'culture/music', 'trust_score': 3.9},
    {'name': 'Teen Vogue', 'url': 'https://www.teenvogue.com/rss', 'country': 'USA', 'bias': 'left', 'trust_score': 3.5},
    {'name': 'Lifehacker', 'url': 'https://lifehacker.com/rss', 'country': 'USA', 'bias': 'tech/lifestyle', 'trust_score': 4.0},
    {'name': 'Eater', 'url': 'https://www.eater.com/rss/index.xml', 'country': 'USA', 'bias': 'lifestyle/food', 'trust_score': 4.1},
    {'name': 'Kotaku', 'url': 'https://kotaku.com/rss', 'country': 'USA', 'bias': 'gaming/culture', 'trust_score': 3.9},
    {'name': 'Polygon', 'url': 'https://www.polygon.com/rss/index.xml', 'country': 'USA', 'bias': 'gaming/culture', 'trust_score': 4.0},
    {'name': 'Lonely Planet', 'url': 'https://www.lonelyplanet.com/news/rss', 'country': 'Global', 'bias': 'neutral', 'trust_score': 4.2},
    {'name': 'Better Homes & Gardens', 'url': 'https://www.bhg.com/rss/all.xml', 'country': 'USA', 'bias': 'lifestyle/home', 'trust_score': 4.0},
    {'name': 'People Magazine', 'url': 'https://people.com/feed', 'country': 'USA', 'bias': 'celebrity/lifestyle', 'trust_score': 3.7},
    {'name': 'Allure', 'url': 'https://www.allure.com/feed/rss', 'country': 'USA', 'bias': 'beauty/lifestyle', 'trust_score': 3.9},
    {'name': 'Travel + Leisure', 'url': 'https://www.travelandleisure.com/rss', 'country': 'USA', 'bias': 'travel/luxury', 'trust_score': 4.1},
    {'name': 'Condé Nast Traveler', 'url': 'https://www.cntraveler.com/rss', 'country': 'USA', 'bias': 'travel/luxury', 'trust_score': 4.1},
    {'name': 'PinkNews', 'url': 'https://www.thepinknews.com/feed/', 'country': 'UK', 'bias': 'lgbtq+', 'trust_score': 4.0},
    {'name': 'LGBTQ Nation', 'url': 'https://www.lgbtqnation.com/feed/', 'country': 'USA', 'bias': 'lgbtq+', 'trust_score': 3.9},
    {'name': 'The Advocate', 'url': 'https://www.advocate.com/feed', 'country': 'USA', 'bias': 'lgbtq+', 'trust_score': 4.0},
    {'name': 'Out Magazine', 'url': 'https://www.out.com/rss.xml', 'country': 'USA', 'bias': 'lgbtq+/culture', 'trust_score': 3.8},
    {'name': 'Gay Times', 'url': 'https://www.gaytimes.co.uk/feed/', 'country': 'UK', 'bias': 'lgbtq+', 'trust_score': 3.9},
    {'name': 'Politico', 'url': 'https://www.politico.com/rss/politics08.xml', 'country': 'USA', 'bias': 'center-left', 'trust_score': 4.1},
    {'name': 'The Hill', 'url': 'https://thehill.com/rss/syndicator/19110', 'country': 'USA', 'bias': 'center', 'trust_score': 4.0},
    {'name': 'Axios', 'url': 'https://www.axios.com/rss', 'country': 'USA', 'bias': 'center', 'trust_score': 4.0},
    {'name': 'RealClearPolitics', 'url': 'https://www.realclearpolitics.com/index.xml', 'country': 'USA', 'bias': 'right-center', 'trust_score': 3.9},
    {'name': 'The Atlantic', 'url': 'https://www.theatlantic.com/feed/all/', 'country': 'USA', 'bias': 'left-center', 'trust_score': 4.2},
    {'name': 'The Daily Beast', 'url': 'https://feeds.thedailybeast.com/rss/articles', 'country': 'USA', 'bias': 'left', 'trust_score': 3.7},
    {'name': 'Newsweek', 'url': 'https://www.newsweek.com/feed', 'country': 'USA', 'bias': 'center', 'trust_score': 3.9},
    {'name': 'Small Wars Journal', 'url': 'https://smallwarsjournal.com/blog/feed', 'country': 'USA', 'bias': 'military/strategy', 'trust_score': 3.8},
    {'name': 'World Politics Review', 'url': 'https://www.worldpoliticsreview.com/feed/', 'country': 'Global', 'bias': 'neutral', 'trust_score': 4.0},
    {'name': 'Defense One', 'url': 'https://www.defenseone.com/rss/news/', 'country': 'USA', 'bias': 'military/defense', 'trust_score': 3.9},
    {'name': 'Yahoo Entertainment',  'url': 'https://news.yahoo.com/rss/entertainment',  'country': 'USA',  'bias': 'center', 'trust_score': 4.0},
       

    # Add more feeds as needed...

]

for feed in rss_feeds:
    print(f"🔄 Fetching from: {feed['name']}")
    
    try:
        parsed = feedparser.parse(feed['url'])
        source_id = get_or_create_source(feed)

        for entry in parsed.entries:
            title = entry.get('title', '').strip()
            raw_content = (entry.get('summary', '') or entry.get('description', '')).strip()
            url = entry.get('link', '').strip()
            published = entry.get('published', '')
            publication_date = datetime.now()

            # Clean the content
            content = clean_text(raw_content)

            # Skip invalid articles
            if not title or not is_valid_content(content):
                print(f"⚠️ Skipping invalid article: {url}")
                continue

            try:
                publication_date = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %Z')
            except:
                try:
                    publication_date = datetime.strptime(published, '%Y-%m-%dT%H:%M:%SZ')
                except:
                    pass  # fallback to now

            hash_value = hashlib.sha256(url.encode()).hexdigest()
            if article_exists(hash_value):
                continue

            topic_cluster_id = get_or_create_topic_cluster("General")

            cursor.execute("""
                INSERT INTO news_articles (
                    title, content, summary, publication_date,
                    url, hash, language, sentiment, bias_label,
                    topic_cluster_id, source_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                title, content, content[:300], publication_date, url,
                hash_value, 'en', 'neutral', feed['bias'], topic_cluster_id, source_id
            ))
            db.commit()
    
    except (http.client.RemoteDisconnected, socket.error, urllib.error.URLError, Exception) as e:
        print(f"❌ Error fetching {feed['name']}: {e}")
        continue

print("✅ All valid news articles inserted successfully.")
cursor.close()
db.close()


