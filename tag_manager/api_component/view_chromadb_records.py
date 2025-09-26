#!/usr/bin/env python3
"""
Script to view ChromaDB records for the RAG system.
"""

import os
import sys
import json
from rag import ComponentRAG, get_rag_instance

def main():
    print("=" * 80)
    print("CHROMADB RECORDS VIEWER")
    print("=" * 80)
    
    # Initialize RAG system
    print("\n1. Initializing RAG system...")
    rag = get_rag_instance()
    
    if not rag.is_initialized:
        print("   RAG system not initialized. Attempting to initialize...")
        if not rag.initialize_rag():
            print("   ❌ Failed to initialize RAG system")
            return
    
    print("   ✅ RAG system initialized successfully")
    
    # Get statistics
    print("\n2. RAG System Statistics:")
    stats = rag.get_statistics()
    for key, value in stats.items():
        if key == 'component_counts':
            print(f"   {key}:")
            for comp, count in value.items():
                print(f"     - {comp}: {count}")
        else:
            print(f"   {key}: {value}")
    
    # Get all records from ChromaDB
    print(f"\n3. ChromaDB Collection Records:")
    print("-" * 50)
    
    try:
        # Query all records
        collection_count = rag.collection.count()
        print(f"Total records in collection: {collection_count}")
        
        if collection_count > 0:
            # Get all records (limit to first 20 to avoid overwhelming output)
            limit = min(20, collection_count)
            results = rag.collection.get(
                include=['documents', 'metadatas'],
                limit=limit
            )
            
            print(f"\nShowing first {limit} records:")
            print("=" * 80)
            
            for i, (doc_id, document, metadata) in enumerate(zip(
                results['ids'], 
                results['documents'], 
                results['metadatas']
            ), 1):
                print(f"\nRecord {i}:")
                print(f"ID: {doc_id}")
                print(f"V1 Component: {metadata.get('v1_component', 'N/A')}")
                print(f"V2 Component: {metadata.get('v2_component', 'N/A')}")
                print(f"Attributes Count: {metadata.get('attributes_count', 0)}")
                
                print(f"\nV1 HTML:")
                print(f"  {metadata.get('v1', 'N/A')[:100]}{'...' if len(metadata.get('v1', '')) > 100 else ''}")
                
                print(f"\nV2 HTML:")
                print(f"  {metadata.get('v2', 'N/A')[:100]}{'...' if len(metadata.get('v2', '')) > 100 else ''}")
                
                print(f"\nSearchable Document (first 200 chars):")
                print(f"  {document[:200]}{'...' if len(document) > 200 else ''}")
                print("-" * 80)
            
            if collection_count > limit:
                print(f"\n... and {collection_count - limit} more records")
        
    except Exception as e:
        print(f"❌ Error retrieving records: {e}")
    
    # Test search functionality
    print(f"\n4. Testing Search Functionality:")
    print("-" * 50)
    
    test_queries = [
        "helix-image",
        "helix-button", 
        "src=",
        "<helix-"
    ]
    
    for query in test_queries:
        print(f"\nSearching for: '{query}'")
        results = rag.search_similar_migrations(query, n_results=3)
        print(f"Found {len(results)} similar migrations:")
        
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result['v1_component']} → {result['v2_component']} "
                  f"(similarity: {result['similarity_score']:.3f})")
    
    print(f"\n" + "=" * 80)
    print("ChromaDB Records View Complete")
    print("=" * 80)

if __name__ == "__main__":
    main()
