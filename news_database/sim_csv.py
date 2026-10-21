import os
from dotenv import load_dotenv
load_dotenv()

import mysql.connector
import csv
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

def fetch_similarity_data():
    """Fetch article similarity data with titles and summaries - DEPRECATED, not used"""
    pass

def clean_text_for_csv(text):
    """Clean text for CSV export - remove newlines and extra spaces"""
    if not text:
        return "No summary available"
    
    # Remove newlines and extra spaces
    cleaned = ' '.join(text.split())
    
    # Limit length if too long
    if len(cleaned) > 500:
        cleaned = cleaned[:497] + "..."
    
    return cleaned

def export_to_csv(output_file="article_similarity.csv"):
    """Export similarity data to CSV file"""
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT 
            a1.title as title1,
            a1.summary as summary1,
            a1.publication_date as date1,
            a1.url as url1,
            a2.title as title2,
            a2.summary as summary2,
            a2.publication_date as date2,
            a2.url as url2,
            sim.similarity_score
        FROM article_similarity sim
        JOIN news_articles a1 ON sim.article_id_1 = a1.id
        JOIN news_articles a2 ON sim.article_id_2 = a2.id
        ORDER BY sim.created_at DESC
    """
    
    print("Fetching similarity data from database...")
    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not data:
        print("No similarity data found in database.")
        return
    
    print(f"Found {len(data)} similarity pairs. Writing to CSV...")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow([
            'Title 1', 
            'Summary 1', 
            'Date 1', 
            'Link 1', 
            'Similarity Score', 
            'Title 2', 
            'Summary 2', 
            'Date 2', 
            'Link 2'
        ])
        
        # Write data rows
        for row in data:
            # Clean summaries
            summary1 = clean_text_for_csv(row['summary1'])
            summary2 = clean_text_for_csv(row['summary2'])
            
            # Format dates
            date1_str = row['date1'].strftime('%d %b %Y') if row['date1'] else "Unknown"
            date2_str = row['date2'].strftime('%d %b %Y') if row['date2'] else "Unknown"
            
            # Format similarity as percentage
            similarity_pct = f"{row['similarity_score'] * 100:.1f}%"
            
            writer.writerow([
                row['title1'],
                summary1,
                date1_str,
                row['url1'] or "N/A",
                similarity_pct,
                row['title2'],
                summary2,
                date2_str,
                row['url2'] or "N/A"
            ])
    
    print(f"Successfully exported to {output_file}")
    print(f"Total records: {len(data)}")

def export_with_sources(output_file="article_similarity_detailed.csv"):
    """Export with additional source information"""
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT 
            a1.title as title1,
            a1.summary as summary1,
            a1.publication_date as date1,
            a1.url as url1,
            ns1.name as source1,
            ns1.bias as bias1,
            sim.similarity_score,
            a2.title as title2,
            a2.summary as summary2,
            a2.publication_date as date2,
            a2.url as url2,
            ns2.name as source2,
            ns2.bias as bias2
        FROM article_similarity sim
        JOIN news_articles a1 ON sim.article_id_1 = a1.id
        JOIN news_articles a2 ON sim.article_id_2 = a2.id
        JOIN news_sources ns1 ON a1.source_id = ns1.id
        JOIN news_sources ns2 ON a2.source_id = ns2.id
        ORDER BY sim.similarity_score DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not results:
        print("No data found.")
        return
    
    print(f"Exporting {len(results)} records with source details...")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Header with source information
        writer.writerow([
            'Title 1',
            'Source 1',
            'Bias 1',
            'Summary 1',
            'Date 1',
            'Link 1',
            'Similarity Score',
            'Title 2',
            'Source 2',
            'Bias 2',
            'Summary 2',
            'Date 2',
            'Link 2'
        ])
        
        for row in results:
            summary1 = clean_text_for_csv(row['summary1'])
            summary2 = clean_text_for_csv(row['summary2'])
            similarity_pct = f"{row['similarity_score'] * 100:.1f}%"
            date1_str = row['date1'].strftime('%d %b %Y') if row['date1'] else "Unknown"
            date2_str = row['date2'].strftime('%d %b %Y') if row['date2'] else "Unknown"
            
            writer.writerow([
                row['title1'],
                row['source1'],
                row['bias1'],
                summary1,
                date1_str,
                row['url1'] or "N/A",
                similarity_pct,
                row['title2'],
                row['source2'],
                row['bias2'],
                summary2,
                date2_str,
                row['url2'] or "N/A"
            ])
    
    print(f"Successfully exported detailed data to {output_file}")

def show_statistics():
    """Show statistics about similarity data"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total_pairs,
            AVG(similarity_score) as avg_similarity,
            MIN(similarity_score) as min_similarity,
            MAX(similarity_score) as max_similarity
        FROM article_similarity
    """)
    stats = cursor.fetchone()
    
    if stats and stats['total_pairs']:
        print("\nSimilarity Statistics:")
        print(f"  Total pairs: {stats['total_pairs']}")
        print(f"  Average similarity: {stats['avg_similarity']*100:.1f}%")
        print(f"  Min similarity: {stats['min_similarity']*100:.1f}%")
        print(f"  Max similarity: {stats['max_similarity']*100:.1f}%")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    print("=== Article Similarity CSV Export ===\n")
    
    # Show statistics first
    show_statistics()
    print()
    
    # Export basic format (your requested format)
    print("Exporting basic format...")
    export_to_csv("article_similarity.csv")
    print()
import mysql.connector
import csv
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

def fetch_similarity_data():
    """Fetch article similarity data with titles and summaries - DEPRECATED, not used"""
    pass

def clean_text_for_csv(text):
    """Clean text for CSV export - remove newlines and extra spaces"""
    if not text:
        return "No summary available"
    
    # Remove newlines and extra spaces
    cleaned = ' '.join(text.split())
    
    # Limit length if too long
    if len(cleaned) > 500:
        cleaned = cleaned[:497] + "..."
    
    return cleaned

def export_to_csv(output_file="article_similarity.csv"):
    """Export similarity data to CSV file"""
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT 
            a1.title as title1,
            a1.summary as summary1,
            a1.publication_date as date1,
            a1.url as url1,
            a2.title as title2,
            a2.summary as summary2,
            a2.publication_date as date2,
            a2.url as url2,
            sim.similarity_score
        FROM article_similarity sim
        JOIN news_articles a1 ON sim.article_id_1 = a1.id
        JOIN news_articles a2 ON sim.article_id_2 = a2.id
        ORDER BY sim.created_at DESC
    """
    
    print("Fetching similarity data from database...")
    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not data:
        print("No similarity data found in database.")
        return
    
    print(f"Found {len(data)} similarity pairs. Writing to CSV...")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow([
            'Title 1', 
            'Summary 1', 
            'Date 1', 
            'Link 1', 
            'Similarity Score', 
            'Title 2', 
            'Summary 2', 
            'Date 2', 
            'Link 2'
        ])
        
        # Write data rows
        for row in data:
            # Clean summaries
            summary1 = clean_text_for_csv(row['summary1'])
            summary2 = clean_text_for_csv(row['summary2'])
            
            # Format dates
            date1_str = row['date1'].strftime('%d %b %Y') if row['date1'] else "Unknown"
            date2_str = row['date2'].strftime('%d %b %Y') if row['date2'] else "Unknown"
            
            # Format similarity as percentage
            similarity_pct = f"{row['similarity_score'] * 100:.1f}%"
            
            writer.writerow([
                row['title1'],
                summary1,
                date1_str,
                row['url1'] or "N/A",
                similarity_pct,
                row['title2'],
                summary2,
                date2_str,
                row['url2'] or "N/A"
            ])
    
    print(f"Successfully exported to {output_file}")
    print(f"Total records: {len(data)}")

def export_with_sources(output_file="article_similarity_detailed.csv"):
    """Export with additional source information"""
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT 
            a1.title as title1,
            a1.summary as summary1,
            a1.publication_date as date1,
            a1.url as url1,
            ns1.name as source1,
            ns1.bias as bias1,
            sim.similarity_score,
            a2.title as title2,
            a2.summary as summary2,
            a2.publication_date as date2,
            a2.url as url2,
            ns2.name as source2,
            ns2.bias as bias2
        FROM article_similarity sim
        JOIN news_articles a1 ON sim.article_id_1 = a1.id
        JOIN news_articles a2 ON sim.article_id_2 = a2.id
        JOIN news_sources ns1 ON a1.source_id = ns1.id
        JOIN news_sources ns2 ON a2.source_id = ns2.id
        ORDER BY sim.similarity_score DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not results:
        print("No data found.")
        return
    
    print(f"Exporting {len(results)} records with source details...")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Header with source information
        writer.writerow([
            'Title 1',
            'Source 1',
            'Bias 1',
            'Summary 1',
            'Date 1',
            'Link 1',
            'Similarity Score',
            'Title 2',
            'Source 2',
            'Bias 2',
            'Summary 2',
            'Date 2',
            'Link 2'
        ])
        
        for row in results:
            summary1 = clean_text_for_csv(row['summary1'])
            summary2 = clean_text_for_csv(row['summary2'])
            similarity_pct = f"{row['similarity_score'] * 100:.1f}%"
            date1_str = row['date1'].strftime('%d %b %Y') if row['date1'] else "Unknown"
            date2_str = row['date2'].strftime('%d %b %Y') if row['date2'] else "Unknown"
            
            writer.writerow([
                row['title1'],
                row['source1'],
                row['bias1'],
                summary1,
                date1_str,
                row['url1'] or "N/A",
                similarity_pct,
                row['title2'],
                row['source2'],
                row['bias2'],
                summary2,
                date2_str,
                row['url2'] or "N/A"
            ])
    
    print(f"Successfully exported detailed data to {output_file}")

def show_statistics():
    """Show statistics about similarity data"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total_pairs,
            AVG(similarity_score) as avg_similarity,
            MIN(similarity_score) as min_similarity,
            MAX(similarity_score) as max_similarity
        FROM article_similarity
    """)
    stats = cursor.fetchone()
    
    if stats and stats['total_pairs']:
        print("\nSimilarity Statistics:")
        print(f"  Total pairs: {stats['total_pairs']}")
        print(f"  Average similarity: {stats['avg_similarity']*100:.1f}%")
        print(f"  Min similarity: {stats['min_similarity']*100:.1f}%")
        print(f"  Max similarity: {stats['max_similarity']*100:.1f}%")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    print("=== Article Similarity CSV Export ===\n")
    
    # Show statistics first
    show_statistics()
    print()
    
    # Export basic format (your requested format)
    print("Exporting basic format...")
    export_to_csv("article_similarity.csv")
    print()
    
    # Ask if user wants detailed export
    response = input("Export detailed version with sources? (yes/no): ").lower()
    if response == 'yes':
        export_with_sources("article_similarity_detailed.csv")
    
    print("\nExport complete!")
    
    # Ask if user wants detailed export
    response = input("Export detailed version with sources? (yes/no): ").lower()
    if response == 'yes':
        export_with_sources("article_similarity_detailed.csv")
    
    print("\nExport complete!")