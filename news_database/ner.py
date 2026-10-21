import os
from dotenv import load_dotenv
load_dotenv()

import spacy
import mysql.connector
from mysql.connector import Error
from collections import defaultdict
import re

nlp = spacy.load("en_core_web_sm")

BATCH_SIZE = 100
MIN_ENTITY_LENGTH = 2
MAX_ENTITY_LENGTH = 100

VALID_ENTITY_TYPES = {
    'PERSON', 'ORG', 'GPE', 'LOC', 'NORP',
    'EVENT', 'LAW', 'PRODUCT', 'WORK_OF_ART',
    'FAC', 'LANGUAGE'
}

NOISE_ENTITIES = {
    'the', 'a', 'an', 'this', 'that', 'these', 'those',
    'he', 'she', 'it', 'they', 'we', 'you',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
    'today', 'yesterday', 'tomorrow', 'one', 'two', 'three',
    'http', 'https', 'www', 'com', 'org', 'net'
}

# Synonym mapping rules
SYNONYM_PATTERNS = {
    'GPE': {
        'United States': ['USA', 'U.S.', 'U.S.A', 'America', 'US', 'United States Of America'],
        'United Kingdom': ['UK', 'U.K.', 'Britain', 'Great Britain'],
        'China': ['PRC', "People's Republic Of China", 'Peoples Republic Of China'],
        'Russia': ['Russian Federation'],
        'South Korea': ['Republic Of Korea', 'Korea'],
        'North Korea': ['DPRK', 'Democratic People\'s Republic Of Korea'],
        'UAE': ['United Arab Emirates', 'U.A.E'],
        'EU': ['European Union'],
        'UN': ['United Nations'],
    },
    'ORG': {
        'WHO': ['World Health Organization'],
        'NATO': ['North Atlantic Treaty Organization'],
        'UN': ['United Nations'],
        'IMF': ['International Monetary Fund'],
        'FBI': ['Federal Bureau Of Investigation'],
        'CIA': ['Central Intelligence Agency'],
        'NASA': ['National Aeronautics And Space Administration'],
        'EU': ['European Union'],
    },
    'PERSON': {
        # This will be handled by fuzzy matching
    }
}

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        autocommit=False
    )

def clean_entity_text(text):
    text = ' '.join(text.split())
    text = text.strip('.,;:!?()[]{}"\'-')
    text = re.sub(r"'s$", "", text)
    return text

def normalize_entity(text):
    """Convert to normalized form for comparison"""
    normalized = text.lower().strip()
    normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove punctuation
    normalized = re.sub(r'\s+', ' ', normalized)  # Normalize spaces
    return normalized

def is_valid_entity(entity_text, entity_label):
    entity_lower = entity_text.lower().strip()
    
    if len(entity_text) < MIN_ENTITY_LENGTH or len(entity_text) > MAX_ENTITY_LENGTH:
        return False
    if entity_lower in NOISE_ENTITIES:
        return False
    if re.match(r'^[\d\W]+$', entity_text):
        return False
    if entity_label not in VALID_ENTITY_TYPES:
        return False
    if any(x in entity_lower for x in ['http', 'www.', '.com', '.org']):
        return False
    if len(set(entity_lower)) < 3 and len(entity_lower) > 4:
        return False
    
    return True

def find_canonical_tag(entity_text, entity_label):
    """Find the canonical tag name for an entity based on synonym patterns"""
    normalized = normalize_entity(entity_text)
    
    # Check predefined patterns
    if entity_label in SYNONYM_PATTERNS:
        for canonical, synonyms in SYNONYM_PATTERNS[entity_label].items():
            canonical_norm = normalize_entity(canonical)
            
            # Check if entity matches canonical
            if normalized == canonical_norm:
                return canonical, None
            
            # Check if entity matches any synonym
            for syn in synonyms:
                syn_norm = normalize_entity(syn)
                if normalized == syn_norm:
                    return canonical, entity_text
    
    # For PERSON entities, handle common patterns
    if entity_label == 'PERSON':
        # President Biden -> Biden
        if normalized.startswith('president '):
            return entity_text.replace('President ', '').strip(), entity_text
        if normalized.startswith('prime minister '):
            return entity_text.replace('Prime Minister ', '').strip(), entity_text
        if normalized.startswith('senator '):
            return entity_text.replace('Senator ', '').strip(), entity_text
        if normalized.startswith('dr ') or normalized.startswith('dr. '):
            return re.sub(r'^dr\.?\s+', '', entity_text, flags=re.IGNORECASE).strip(), entity_text
    
    return entity_text, None

def extract_clean_entities(text):
    if not text or len(text.strip()) < 10:
        return {}
    
    text = text[:10000]
    doc = nlp(text)
    entity_dict = defaultdict(set)
    
    for ent in doc.ents:
        cleaned_text = clean_entity_text(ent.text)
        
        if is_valid_entity(cleaned_text, ent.label_):
            entity_dict[ent.label_].add(cleaned_text)
    
    return entity_dict

def get_or_create_tag_with_synonym(cursor, entity, label):
    """Get or create tag, handling synonyms. Returns (tag_id, is_synonym)"""
    
    # Find canonical form
    canonical, synonym_text = find_canonical_tag(entity, label)
    
    # Check if canonical tag exists
    cursor.execute(
        "SELECT id FROM tags WHERE name = %s AND label = %s",
        (canonical, label)
    )
    result = cursor.fetchone()
    
    if result:
        tag_id = result[0] if isinstance(result, tuple) else result["id"]
        
        # If this is a synonym variant, record it
        if synonym_text and synonym_text != canonical:
            cursor.execute(
                "SELECT id FROM tag_synonyms WHERE synonym = %s AND tag_id = %s",
                (synonym_text, tag_id)
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO tag_synonyms (synonym, tag_id) VALUES (%s, %s)",
                    (synonym_text, tag_id)
                )
        
        return tag_id, bool(synonym_text)
    
    # Create new canonical tag
    cursor.execute(
        "INSERT INTO tags (name, label) VALUES (%s, %s)",
        (canonical, label)
    )
    tag_id = cursor.lastrowid
    
    # If original was a synonym, record it
    if synonym_text and synonym_text != canonical:
        cursor.execute(
            "INSERT INTO tag_synonyms (synonym, tag_id) VALUES (%s, %s)",
            (synonym_text, tag_id)
        )
    
    return tag_id, bool(synonym_text)

def link_article_tag(cursor, article_id, tag_id):
    cursor.execute(
        "INSERT IGNORE INTO article_tags (article_id, tag_id) VALUES (%s, %s)",
        (article_id, tag_id)
    )

def get_last_processed_id(cursor):
    cursor.execute("SELECT MAX(article_id) as last_id FROM article_tags")
    result = cursor.fetchone()
    if result and result['last_id']:
        return result['last_id']
    return 0

def fetch_articles_batch(cursor, start_id, batch_size):
    query = """
        SELECT id, title, summary, content 
        FROM news_articles 
        WHERE id > %s 
        ORDER BY id 
        LIMIT %s
    """
    cursor.execute(query, (start_id, batch_size))
    return cursor.fetchall()

def process_articles_with_synonyms():
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        last_processed = get_last_processed_id(cursor)
        print(f"Starting from article ID: {last_processed}")
        
        cursor.execute("SELECT COUNT(*) as total FROM news_articles WHERE id > %s", (last_processed,))
        total_remaining = cursor.fetchone()["total"]
        print(f"Total articles to process: {total_remaining}")
        
        processed_count = 0
        total_tags_added = 0
        total_synonyms_found = 0
        current_id = last_processed
        
        while True:
            articles = fetch_articles_batch(cursor, current_id, BATCH_SIZE)
            
            if not articles:
                break
            
            batch_tags = 0
            batch_synonyms = 0
            
            for article in articles:
                article_id = article["id"]
                current_id = article_id
                
                title = article.get("title") or ""
                summary = article.get("summary") or ""
                content = article.get("content") or ""
                
                if len(summary) < 50 and len(content) > 0:
                    text = f"{title}. {content[:2000]}"
                else:
                    text = f"{title}. {summary}"
                
                if not text.strip():
                    continue
                
                entity_dict = extract_clean_entities(text)
                
                if not entity_dict:
                    continue
                
                article_tag_count = 0
                article_synonym_count = 0
                
                for label, entities in entity_dict.items():
                    for entity in entities:
                        tag_id, is_synonym = get_or_create_tag_with_synonym(cursor, entity, label)
                        link_article_tag(cursor, article_id, tag_id)
                        article_tag_count += 1
                        if is_synonym:
                            article_synonym_count += 1
                
                batch_tags += article_tag_count
                batch_synonyms += article_synonym_count
                processed_count += 1
                
                if processed_count % 10 == 0:
                    print(f"Processed: {processed_count}/{total_remaining} | "
                          f"Article {article_id} | Tags: {article_tag_count} | "
                          f"Synonyms: {article_synonym_count}")
            
            db.commit()
            total_tags_added += batch_tags
            total_synonyms_found += batch_synonyms
            print(f"Batch committed: {len(articles)} articles, {batch_tags} tags, {batch_synonyms} synonyms")
            print("-" * 70)
        
        print(f"\nNER processing completed!")
        print(f"Total articles processed: {processed_count}")
        print(f"Total tag links created: {total_tags_added}")
        print(f"Total synonyms detected: {total_synonyms_found}")
        
        # Statistics
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT article_id) as articles_with_tags,
                COUNT(*) as total_links,
                AVG(tag_count) as avg_tags_per_article
            FROM (
                SELECT article_id, COUNT(*) as tag_count
                FROM article_tags
                GROUP BY article_id
            ) as stats
        """)
        stats = cursor.fetchone()
        
        if stats:
            print(f"\nTag Statistics:")
            print(f"  Articles with tags: {stats['articles_with_tags']}")
            print(f"  Total tag links: {stats['total_links']}")
            print(f"  Avg tags per article: {stats['avg_tags_per_article']:.2f}")
        
        cursor.execute("SELECT COUNT(*) as total FROM tags")
        tag_count = cursor.fetchone()["total"]
        print(f"  Unique canonical tags: {tag_count}")
        
        cursor.execute("SELECT COUNT(*) as total FROM tag_synonyms")
        synonym_count = cursor.fetchone()["total"]
        print(f"  Total synonyms recorded: {synonym_count}")
        
        # Show top tags
        cursor.execute("""
            SELECT t.name, t.label, COUNT(at.article_id) as article_count
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            GROUP BY t.id
            ORDER BY article_count DESC
            LIMIT 10
        """)
        print(f"\nTop 10 Most Common Tags:")
        for row in cursor.fetchall():
            print(f"  {row['name']} ({row['label']}): {row['article_count']} articles")
        
        cursor.close()
        db.close()
        
    except Error as e:
        print(f"Database error: {e}")
        if db:
            db.rollback()
    except KeyboardInterrupt:
        print("\nProcess interrupted. Progress has been saved.")
        db.commit()
        cursor.close()
        db.close()

if __name__ == "__main__":
    print("=== NER with Tag Synonym Detection ===")
    print("This will normalize entities like 'USA' -> 'United States'")
    print("and track all variants as synonyms.")
    print()
    
    process_articles_with_synonyms()