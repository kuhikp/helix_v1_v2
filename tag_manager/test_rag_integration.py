#!/usr/bin/env python3
"""
Test script for the updated RAG system with database integration.
"""
import os
import sys
import django

# Add the Django project to the Python path
sys.path.append('/Applications/Projects/commit_v1_v2/tag_manager')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tag_manager.settings')

# Setup Django
django.setup()

# Import the RAG functions
from api_component.rag import (
    get_rag_statistics, 
    update_rag, 
    reset_rag, 
    search_migrations,
    get_migration_suggestion,
    force_reload_rag
)

def test_rag_system():
    """Test the RAG system with database integration."""
    print("=== Testing RAG System with Database Integration ===\n")
    
    # Test 1: Get initial statistics
    print("1. Getting RAG system statistics...")
    stats = get_rag_statistics()
    print(f"   Total migrations: {stats.get('total_migrations', 'N/A')}")
    print(f"   ChromaDB documents: {stats.get('chromadb_documents', 'N/A')}")
    print(f"   Django available: {stats.get('django_available', 'N/A')}")
    if 'database_stats' in stats:
        db_stats = stats['database_stats']
        print(f"   Total KB entries: {db_stats.get('total_knowledge_base_entries', 'N/A')}")
        print(f"   Active KB entries: {db_stats.get('active_knowledge_base_entries', 'N/A')}")
    print()
    
    # Test 2: Force reload with database data
    print("2. Force reloading RAG with database data...")
    success = force_reload_rag(use_database=True)
    print(f"   Success: {success}")
    
    if success:
        # Get updated statistics
        updated_stats = get_rag_statistics()
        print(f"   Updated total migrations: {updated_stats.get('total_migrations', 'N/A')}")
        
        data_sources = updated_stats.get('data_sources', {})
        print(f"   Database entries: {data_sources.get('database_entries', 'N/A')}")
        print(f"   CSV entries: {data_sources.get('csv_entries', 'N/A')}")
    print()
    
    # Test 3: Test search functionality
    print("3. Testing search functionality...")
    query = "helix-image"
    results = search_migrations(query, n_results=3)
    print(f"   Found {len(results)} results for query: '{query}'")
    for i, result in enumerate(results[:2], 1):  # Show first 2 results
        print(f"   Result {i}:")
        print(f"     Component: {result.get('v1_component', 'N/A')} -> {result.get('v2_component', 'N/A')}")
        print(f"     Similarity: {result.get('similarity_score', 'N/A'):.3f}")
    print()
    
    # Test 4: Test migration suggestion
    print("4. Testing migration suggestion...")
    v1_sample = '<helix-image src="test.jpg" alt="Test"></helix-image>'
    suggestion = get_migration_suggestion(v1_sample, use_ollama=False)  # Disable Ollama for testing
    
    if 'error' not in suggestion:
        print(f"   Input: {suggestion.get('input_v1', 'N/A')}")
        print(f"   Suggested V2: {suggestion.get('suggested_v2', 'N/A')}")
        print(f"   Confidence: {suggestion.get('confidence_score', 'N/A'):.3f}")
        print(f"   Method: {suggestion.get('method', 'N/A')}")
        print(f"   Similar examples found: {len(suggestion.get('similar_examples', []))}")
    else:
        print(f"   Error: {suggestion['error']}")
    print()
    
    print("=== RAG System Test Complete ===")

if __name__ == "__main__":
    test_rag_system()