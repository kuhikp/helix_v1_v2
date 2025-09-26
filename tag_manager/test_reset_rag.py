#!/usr/bin/env python3
"""
Test script to run reset_rag and load from Knowledge Base.
"""

import sys
import os
import django

# Add the Django project path
sys.path.insert(0, '/Applications/Projects/commit_v1_v2/tag_manager')

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tag_manager.settings')
django.setup()

# Import after Django setup
from api_component.rag import reset_rag, get_rag_statistics, get_rag_instance

def test_reset_rag_with_knowledge_base():
    """Test resetting RAG system and loading from Knowledge Base."""
    print("=" * 80)
    print("🧠 Testing RAG System Reset with Knowledge Base Integration")
    print("=" * 80)
    
    try:
        # Get initial statistics
        print("\n📊 Getting initial RAG statistics...")
        initial_stats = get_rag_statistics()
        print(f"Initial stats: {initial_stats}")
        
        # Reset RAG system with database data
        print("\n🔄 Resetting RAG system and loading from Knowledge Base...")
        success = reset_rag(use_database=True)
        
        if success:
            print("✅ RAG system reset successful!")
        else:
            print("❌ RAG system reset failed!")
            return False
        
        # Get updated statistics
        print("\n📊 Getting updated RAG statistics after reset...")
        updated_stats = get_rag_statistics()
        
        print("\n" + "=" * 50)
        print("📈 RAG SYSTEM STATISTICS")
        print("=" * 50)
        
        if 'error' in updated_stats:
            print(f"❌ Error: {updated_stats['error']}")
            return False
        
        # Display key statistics
        print(f"🗂️  Total migrations: {updated_stats.get('total_migrations', 0)}")
        print(f"🗄️  ChromaDB documents: {updated_stats.get('chromadb_documents', 0)}")
        print(f"🏷️  Component types: {updated_stats.get('component_types', 0)}")
        print(f"🔧 Is initialized: {updated_stats.get('is_initialized', False)}")
        print(f"🐍 Django available: {updated_stats.get('django_available', False)}")
        
        # Data sources breakdown
        data_sources = updated_stats.get('data_sources', {})
        print(f"\n📊 DATA SOURCES:")
        print(f"   Database entries: {data_sources.get('database_entries', 0)}")
        print(f"   CSV entries: {data_sources.get('csv_entries', 0)}")
        
        # Database statistics
        db_stats = updated_stats.get('database_stats', {})
        if db_stats and 'database_error' not in db_stats:
            print(f"\n🗃️  DATABASE STATS:")
            print(f"   Total Knowledge Base entries: {db_stats.get('total_knowledge_base_entries', 0)}")
            print(f"   Active entries: {db_stats.get('active_knowledge_base_entries', 0)}")
            print(f"   Inactive entries: {db_stats.get('inactive_knowledge_base_entries', 0)}")
        elif 'database_error' in db_stats:
            print(f"\n❌ Database error: {db_stats['database_error']}")
        
        # Component breakdown
        component_counts = updated_stats.get('component_counts', {})
        if component_counts:
            print(f"\n🏷️  COMPONENT BREAKDOWN:")
            for component, count in sorted(component_counts.items()):
                if component:  # Skip empty component names
                    print(f"   {component}: {count} migrations")
        
        # Test a simple search
        print(f"\n🔍 Testing search functionality...")
        rag = get_rag_instance()
        test_results = rag.search_similar_migrations("helix-image", n_results=3)
        
        if test_results:
            print(f"✅ Search test successful! Found {len(test_results)} results")
            for i, result in enumerate(test_results, 1):
                print(f"   {i}. Component: {result['v1_component']} → {result['v2_component']}")
                print(f"      Similarity: {result['similarity_score']:.3f}")
        else:
            print("⚠️  Search test returned no results")
        
        print("\n" + "=" * 80)
        print("🎉 RAG SYSTEM RESET AND KNOWLEDGE BASE LOADING TEST COMPLETE!")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during RAG reset test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_reset_rag_with_knowledge_base()