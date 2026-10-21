import os
from dotenv import load_dotenv
load_dotenv()

import mysql.connector
import numpy as np
import faiss
from datetime import datetime
from collections import defaultdict
import logging

logging.basicConfig(
    filename="similarity_faiss.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DB = {
    "host": "localhost",
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

DIM = 384
SIMILARITY_THRESHOLD = 0.65  # Lower threshold for more matches

def fetch_articles_by_date_topic():
    """Fetch all articles grouped by publication date and topic"""
    with mysql.connector.connect(**DB) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT 
                a.id,
                DATE(a.publication_date) as pub_date,
                a.topic_cluster_id,
                a.source_id,
                e.embedding_vector
            FROM news_articles a
            JOIN article_embeddings e ON a.id = e.article_id
            WHERE e.embedding_vector IS NOT NULL
            ORDER BY pub_date, topic_cluster_id
        """)
        return cur.fetchall()

def group_articles_by_date_topic(articles):
    """Group articles by date and topic"""
    groups = defaultdict(list)
    
    for aid, pub_date, topic_id, source_id, emb_blob in articles:
        if emb_blob:
            emb = np.frombuffer(emb_blob, dtype=np.float32, count=DIM)
            key = (pub_date, topic_id or 0)  # Group by date and topic
            groups[key].append({
                'id': aid,
                'source_id': source_id,
                'embedding': emb
            })
    
    return groups

def store_similarities_batch(similarities):
    """Store multiple similarities at once"""
    if not similarities:
        return
    
    with mysql.connector.connect(**DB) as conn, conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO article_similarity 
            (article_id_1, article_id_2, similarity_score, method, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, similarities)
        conn.commit()
    
    logging.info(f"Stored {len(similarities)} similarity pairs")

def compare_group_with_faiss(articles, threshold=SIMILARITY_THRESHOLD):
    """Compare all articles in a group using FAISS"""
    if len(articles) < 2:
        return []
    
    # Separate articles by source to ensure cross-source comparisons
    source_groups = defaultdict(list)
    for art in articles:
        source_groups[art['source_id']].append(art)
    
    # Skip if only one source in this group
    if len(source_groups) < 2:
        return []
    
    similarities = []
    
    # Compare articles from different sources
    sources = list(source_groups.keys())
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            source1_articles = source_groups[sources[i]]
            source2_articles = source_groups[sources[j]]
            
            # Build FAISS index for source2
            ids2 = [art['id'] for art in source2_articles]
            vecs2 = np.array([art['embedding'] for art in source2_articles], dtype=np.float32)
            
            # Normalize for cosine similarity
            faiss.normalize_L2(vecs2)
            
            # Build index
            index = faiss.IndexFlatIP(DIM)
            index.add(vecs2)
            
            # Compare each article from source1
            for art1 in source1_articles:
                vec1 = art1['embedding'].reshape(1, -1).astype(np.float32)
                faiss.normalize_L2(vec1)
                
                # Search
                D, I = index.search(vec1, min(5, len(ids2)))  # Top 5 matches
                
                for idx, score in zip(I[0], D[0]):
                    if score >= threshold:
                        similarities.append((
                            art1['id'],
                            ids2[idx],
                            float(score),
                            "faiss_cosine_date_topic",
                            datetime.now()
                        ))
    
    return similarities

def pipeline_optimized(threshold=SIMILARITY_THRESHOLD):
    """Optimized pipeline that groups by date and topic"""
    print("Fetching articles...")
    articles = fetch_articles_by_date_topic()
    print(f"Fetched {len(articles)} articles with embeddings")
    
    print("Grouping by date and topic...")
    groups = group_articles_by_date_topic(articles)
    print(f"Created {len(groups)} groups")
    
    all_similarities = []
    processed_groups = 0
    
    for (pub_date, topic_id), group_articles in groups.items():
        if len(group_articles) < 2:
            continue
        
        # Count unique sources in this group
        unique_sources = len(set(art['source_id'] for art in group_articles))
        if unique_sources < 2:
            continue
        
        print(f"Processing group: Date={pub_date}, Topic={topic_id}, Articles={len(group_articles)}, Sources={unique_sources}")
        
        similarities = compare_group_with_faiss(group_articles, threshold)
        all_similarities.extend(similarities)
        
        # Store in batches of 100
        if len(all_similarities) >= 100:
            store_similarities_batch(all_similarities)
            print(f"Stored batch of {len(all_similarities)} similarities")
            all_similarities = []
        
        processed_groups += 1
        if processed_groups % 10 == 0:
            print(f"Processed {processed_groups}/{len(groups)} groups")
    
    # Store remaining similarities
    if all_similarities:
        store_similarities_batch(all_similarities)
        print(f"Stored final batch of {len(all_similarities)} similarities")
    
    print(f"Pipeline finished. Processed {processed_groups} groups")
    logging.info(f"Pipeline finished. Processed {processed_groups} groups")

def clear_old_similarities():
    """Clear existing similarities before running"""
    response = input("Clear existing similarities? (yes/no): ")
    if response.lower() == 'yes':
        with mysql.connector.connect(**DB) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM article_similarity WHERE method = 'faiss_cosine_date_topic'")
            conn.commit()
            print(f"Cleared old similarities")

if __name__ == "__main__":
    print("=== Optimized Article Similarity Analysis ===")
    print("This will compare articles from the SAME DATE and SAME TOPIC")
    print("Only compares articles from DIFFERENT sources")
    print()
    
    # Optionally clear old data
    # clear_old_similarities()
    
    # Run the pipeline
    pipeline_optimized(threshold=SIMILARITY_THRESHOLD)
    
    # Show statistics
    with mysql.connector.connect(**DB) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   AVG(similarity_score) as avg_score,
                   MIN(similarity_score) as min_score,
                   MAX(similarity_score) as max_score
            FROM article_similarity
            WHERE method = 'faiss_cosine_date_topic'
        """)
        stats = cur.fetchone()
        if stats and stats[0]:
            print(f"\nStatistics:")
            print(f"  Total pairs: {stats[0]}")
            print(f"  Avg similarity: {stats[1]:.4f}")
            print(f"  Min similarity: {stats[2]:.4f}")
            print(f"  Max similarity: {stats[3]:.4f}")












