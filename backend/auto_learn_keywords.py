"""Auto-learning system for key identifier extraction from catalog data"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path
from collections import defaultdict
import re

load_dotenv(Path(__file__).parent / '.env')

async def analyze_catalog_and_generate_keywords():
    """Analyze all products to automatically generate key identifiers
    
    Strategy:
    1. Group products by super_class
    2. Extract all significant words from each group
    3. Find discriminating words (appear in <30% of category)
    4. Generate keyword sets automatically
    """
    
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    print("🤖 AUTO-LEARNING: Analyzing 8,218 products...")
    print("="*70)
    
    # Get all supplier_items with their categories
    items = await db.supplier_items.find(
        {'active': True},
        {'_id': 0, 'name_raw': 1, 'super_class': 1}
    ).to_list(10000)
    
    # Group by category
    category_words = defaultdict(lambda: defaultdict(int))
    category_counts = defaultdict(int)
    
    # Common words to ignore
    stopwords = {
        'в', 'с', 'и', 'на', 'для', 'из', 'по', 'от', 'до', 'кг', 'г', 'гр', 'л', 'мл',
        'шт', 'пакет', 'упак', 'кор', 'ведро', 'бут', 'bottle', 'pack', 'box',
        'вес', 'weight', '~', 'ок', 'около', 'approx', 'russia', 'россия',
        'гост', 'ту', 'тм', 'tm', 'brand'
    }
    
    for item in items:
        category = item.get('super_class', 'other')
        name = item.get('name_raw', '').lower()
        
        # Extract words (alphanumeric only)
        words = re.findall(r'[а-яa-z0-9]+', name)
        
        # Filter significant words (length > 3, not stopwords)
        significant_words = [w for w in words if len(w) > 3 and w not in stopwords]
        
        for word in significant_words:
            category_words[category][word] += 1
        
        category_counts[category] += 1
    
    print(f"\n✅ Analyzed {len(items)} products across {len(category_counts)} categories")
    
    # Find discriminating words for each category
    print(f"\n🎯 Generating category-specific keywords...")
    print(f"="*70)
    
    category_keywords = {}
    
    for category, words in category_words.items():
        if category_counts[category] < 5:  # Skip small categories
            continue
        
        # Find words that appear in 10-30% of items (discriminating, not universal)
        discriminating = []
        
        for word, count in words.items():
            frequency = count / category_counts[category]
            
            # Discriminating words: appear in some items but not all
            if 0.05 <= frequency <= 0.40:  # 5-40% of items
                discriminating.append((word, count, frequency))
        
        # Sort by count (most common discriminating words)
        discriminating.sort(key=lambda x: x[1], reverse=True)
        
        # Take top 50 discriminating words per category
        category_keywords[category] = [w[0] for w in discriminating[:50]]
        
        if len(category_keywords[category]) > 0:
            print(f"\n{category:40} ({category_counts[category]:4} items):")
            print(f"  Top keywords: {', '.join(category_keywords[category][:10])}")
    
    # Generate Python code for key_identifiers
    print(f"\n{'='*70}")
    print(f"📝 GENERATED KEY_IDENTIFIERS CODE:")
    print(f"{'='*70}\n")
    
    all_keywords = set()
    for keywords in category_keywords.values():
        all_keywords.update(keywords[:20])  # Top 20 per category
    
    print(f"# AUTO-GENERATED from {len(items)} products")
    print(f"# Total unique discriminating keywords: {len(all_keywords)}")
    print(f"key_words = {{")
    
    for i, word in enumerate(sorted(all_keywords), 1):
        print(f"    '{word}',", end='')
        if i % 5 == 0:
            print()
    
    print("\n}")
    
    # Save to file
    output_file = Path(__file__).parent / 'auto_generated_keywords.py'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# AUTO-GENERATED KEY IDENTIFIERS\n")
        f.write(f"# Generated from {len(items)} products\n")
        f.write(f"# {len(all_keywords)} unique discriminating keywords\n\n")
        f.write(f"AUTO_KEYWORDS = {{\n")
        for word in sorted(all_keywords):
            f.write(f"    '{word}',\n")
        f.write(f"}}\n")
    
    print(f"\n✅ Saved to {output_file}")
    
    # Statistics
    print(f"\n{'='*70}")
    print(f"📊 STATISTICS:")
    print(f"{'='*70}")
    print(f"Total keywords generated: {len(all_keywords)}")
    print(f"Categories analyzed: {len(category_keywords)}")
    print(f"Products analyzed: {len(items)}")
    
    await client.close()

if __name__ == '__main__':
    asyncio.run(analyze_catalog_and_generate_keywords())
