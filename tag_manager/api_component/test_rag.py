#!/usr/bin/env python3
"""
Test script for the RAG system functionality.
Can be run independently to test RAG features.
"""

import os
import sys

# Add the project path to Python path
project_path = os.path.dirname(os.path.dirname(__file__))
sys.path.append(project_path)

def test_rag_system():
    """Test the RAG system functionality."""
    print("Testing RAG System for Helix Component Migration")
    print("=" * 50)
    
    try:
        # Import RAG module
        from rag import ComponentRAG
        
        # Initialize RAG system
        print("1. Initializing RAG system...")
        rag = ComponentRAG()
        
        success = rag.initialize_rag(force_reload=True)
        if not success:
            print("❌ Failed to initialize RAG system")
            return False
        
        print("✅ RAG system initialized successfully")
        
        # Test statistics
        print("\n2. Getting system statistics...")
        stats = rag.get_statistics()
        
        if 'error' in stats:
            print(f"❌ Error getting stats: {stats['error']}")
            return False
        
        print(f"✅ Total migrations: {stats['total_migrations']}")
        print(f"✅ ChromaDB documents: {stats['chromadb_documents']}")
        print(f"✅ Component types: {stats['component_types']}")
        
        # Test search functionality
        print("\n3. Testing search functionality...")
        test_query = "helix-image"
        similar_migrations = rag.search_similar_migrations(test_query, n_results=3)
        
        print(f"✅ Found {len(similar_migrations)} similar migrations for '{test_query}'")
        
        for i, migration in enumerate(similar_migrations, 1):
            print(f"   {i}. {migration['v1_component']} -> {migration['v2_component']} "
                  f"(similarity: {migration['similarity_score']:.3f})")
        
        # Test migration suggestion
        print("\n4. Testing migration suggestion...")
        test_v1_html = '<helix-image alt="Test Image" src="test.jpg"></helix-image>'
        
        suggestion = rag.get_migration_suggestion(test_v1_html, use_ollama=False)
        
        if 'error' in suggestion:
            print(f"❌ Migration suggestion error: {suggestion['error']}")
        else:
            print(f"✅ Migration suggestion generated")
            print(f"   Method: {suggestion['method']}")
            print(f"   Confidence: {suggestion['confidence_score']:.3f}")
            if suggestion['suggested_v2']:
                print(f"   V2 Suggestion: {suggestion['suggested_v2'][:100]}...")
        
        # Test component breakdown
        if stats['component_counts']:
            print("\n5. Component breakdown:")
            for component, count in stats['component_counts'].items():
                print(f"   {component}: {count}")
        
        print("\n✅ All RAG tests completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("pip install chromadb beautifulsoup4 requests")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_csv_loading():
    """Test CSV loading functionality."""
    print("\nTesting CSV Loading")
    print("=" * 20)
    
    try:
        from rag import ComponentRAG
        
        # Test with default CSV path
        rag = ComponentRAG()
        csv_data = rag.load_csv_data()
        
        print(f"✅ Loaded {len(csv_data)} records from CSV")
        
        if csv_data:
            # Show first record
            first_record = csv_data[0]
            print(f"✅ First record:")
            print(f"   V1 Component: {first_record['v1_component']}")
            print(f"   V2 Component: {first_record['v2_component']}")
            print(f"   Attributes: {len(first_record['attributes'])}")
            
        return len(csv_data) > 0
        
    except Exception as e:
        print(f"❌ CSV loading error: {e}")
        return False

if __name__ == "__main__":
    print("RAG System Test Suite")
    print("====================")
    
    # Test CSV loading first
    csv_success = test_csv_loading()
    
    if csv_success:
        # Test full RAG system
        rag_success = test_rag_system()
        
        if rag_success:
            print("\n🎉 All tests passed! RAG system is ready to use.")
            
            print("\nNext steps:")
            print("1. Start your Django server: python manage.py runserver")
            print("2. Use the RAG API endpoints:")
            print("   - POST /api_component/rag/migrate/ - Get migration suggestions")
            print("   - POST /api_component/rag/search/ - Search similar components")
            print("   - GET /api_component/rag/stats/ - Get system statistics")
            
        else:
            print("\n❌ Some tests failed. Check the error messages above.")
            sys.exit(1)
    else:
        print("\n❌ CSV loading failed. Check if v1_v2.csv exists and is readable.")
        sys.exit(1)
