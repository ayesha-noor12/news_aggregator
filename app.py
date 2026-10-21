import os
from dotenv import load_dotenv
load_dotenv()

# app.py
from flask import Flask, render_template, request, jsonify
import mysql.connector
from mysql.connector import Error
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "autocommit": True
}

def get_db_connection():
    """Get database connection with error handling"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        return None

def get_article(article_id):
    """Get article by ID with error handling"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT na.id, na.title, na.content, na.summary, na.publication_date, 
                   na.url, na.bias_label, na.sentiment, na.language,
                   ns.name as source_name, ns.country, ns.bias as source_bias, 
                   ns.trust_score, ns.url as source_url
            FROM news_articles na 
            JOIN news_sources ns ON na.source_id = ns.id 
            WHERE na.id=%s
        """, (article_id,))
        article = cur.fetchone()
        
        # Clean up and add fallback values if data is missing
        if article:
            # Use article bias_label if available, otherwise source bias
            article['bias'] = article.get('bias_label') or article.get('source_bias') or 'center'
            article['trust_score'] = article.get('trust_score') or 4.0
            article['source_name'] = article.get('source_name') or 'Unknown Source'
            article['country'] = article.get('country') or 'Unknown'
            
            # Handle summary
            if not article.get('summary') or len(article.get('summary', '').strip()) < 20:
                content = article.get('content', '')
                if content and len(content) > 50:
                    article['summary'] = content[:300] + '...' if len(content) > 300 else content
                else:
                    article['summary'] = 'No summary available'
        
        return article
    except Error as e:
        logger.error(f"Error fetching article {article_id}: {e}")
        return None
    finally:
        if conn.is_connected():
            conn.close()

def get_similarity_pair(limit=1, offset=0):
    """Get similarity pairs with pagination support"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT article_id_1, article_id_2, similarity_score, created_at
            FROM article_similarity 
            ORDER BY created_at DESC 
            LIMIT %s OFFSET %s
        """, (limit, offset))
        if limit == 1:
            pair = cur.fetchone()
        else:
            pair = cur.fetchall()
        return pair
    except Error as e:
        logger.error(f"Error fetching similarity pairs: {e}")
        return None
    finally:
        if conn.is_connected():
            conn.close()

def get_total_similarity_pairs():
    """Get total count of similarity pairs"""
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM article_similarity")
        count = cur.fetchone()[0]
        return count
    except Error as e:
        logger.error(f"Error counting similarity pairs: {e}")
        return 0
    finally:
        if conn.is_connected():
            conn.close()

@app.route("/")
def show_comparison():
    """Show the most recent similarity comparison"""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 1
        offset = (page - 1) * per_page
        
        # Get similarity pair
        pair = get_similarity_pair(limit=1, offset=offset)
        if not pair:
            return render_template("error.html", 
                                 message="No similarity data available. Please run the similarity calculation first.")

        # Get articles
        a1 = get_article(pair["article_id_1"])
        a2 = get_article(pair["article_id_2"])
        
        if not a1 or not a2:
            return render_template("error.html", 
                                 message="One or more articles could not be found.")

        # Calculate similarity percentage
        score = int(pair["similarity_score"] * 100)
        
        # Get pagination info
        total_pairs = get_total_similarity_pairs()
        has_prev = page > 1
        has_next = offset + per_page < total_pairs
        
        return render_template("comparison.html", 
                             article1=a1, 
                             article2=a2, 
                             score=score,
                             pair_date=pair["created_at"],
                             page=page,
                             has_prev=has_prev,
                             has_next=has_next,
                             total_pairs=total_pairs)
                             
    except Exception as e:
        logger.error(f"Error in show_comparison: {e}")
        return render_template("error.html", 
                             message="An error occurred while loading the comparison.")

@app.route("/api/similarity-pairs")
def api_similarity_pairs():
    """API endpoint to get similarity pairs as JSON"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        offset = (page - 1) * per_page
        
        pairs = get_similarity_pair(limit=per_page, offset=offset)
        total = get_total_similarity_pairs()
        
        if not pairs:
            return jsonify({"error": "No similarity data available"}), 404
            
        return jsonify({
            "pairs": pairs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_next": offset + per_page < total,
            "has_prev": page > 1
        })
        
    except Exception as e:
        logger.error(f"Error in API endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/article/<int:article_id>")
def show_article(article_id):
    """Show individual article details"""
    try:
        article = get_article(article_id)
        if not article:
            return render_template("error.html", 
                                 message="Article not found.")
        
        return render_template("article.html", article=article)
        
    except Exception as e:
        logger.error(f"Error showing article {article_id}: {e}")
        return render_template("error.html", 
                             message="An error occurred while loading the article.")

@app.errorhandler(404)
def page_not_found(e):
    return render_template("error.html", message="Page not found."), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("error.html", message="Internal server error."), 500

if __name__ == "__main__":
    app.run(debug=True)

