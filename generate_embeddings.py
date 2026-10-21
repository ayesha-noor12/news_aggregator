import os
from dotenv import load_dotenv
load_dotenv()

import mysql.connector
from sentence_transformers import SentenceTransformer
import numpy as np

DB = {
    "host": "localhost",
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

def generate_and_store_embeddings(batch_size=500):
    conn = mysql.connector.connect(**DB)
    cur = conn.cursor()

    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Fetch all articles that do not have embeddings yet
    cur.execute("""
        SELECT a.id, a.title, a.content
        FROM news_articles a
        LEFT JOIN article_embeddings e ON a.id = e.article_id
        WHERE e.article_id IS NULL
    """)
    articles = cur.fetchall()
    total = len(articles)

    print(f"📌 Found {total} new articles without embeddings")

    for idx, (article_id, title, content) in enumerate(articles, start=1):
        text = f"{title or ''} {content or ''}"

        try:
            # Generate embedding
            emb = model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True
            ).astype(np.float32)

            emb_bytes = emb.tobytes()

            cur.execute("""
                INSERT INTO article_embeddings (article_id, embedding_vector)
                VALUES (%s, %s)
            """, (article_id, emb_bytes))

        except Exception as e:
            print(f"❌ Error processing article {article_id}: {e}")
            continue

        # Commit in batches
        if idx % batch_size == 0:
            conn.commit()
            print(f"✅ Processed {idx}/{total} articles...")

    # Final commit
    conn.commit()
    conn.close()
    print("🏁 Embedding generation complete!")

if __name__ == "__main__":
    generate_and_store_embeddings(batch_size=500)

