import os
import glob
import re

replacements = {
    # Customer context
    r'Total Purchases': 'Total Spend',
    r'Recent Purchases': 'Recent Orders',
    
    # Inventory context - Sidebar & Dashboard
    r'>Purchases<': '>Stock In<',
    r'>Purchase Orders<': '>Stock In Records<',
    r'>New Purchase<': '>Add Stock<',
    r'>New Purchase Order<': '>Add Stock<',
    
    # Inventory context - Forms and Tables
    r'Purchase Date': 'Stock Date',
    r'Purchase Number': 'Reference Number',
    r'Purchase Order:': 'Stock In Record:',
    r'Purchase Items': 'Stock Items',
    r'Purchase Details': 'Stock In Details',
    r'Save Purchase': 'Save Stock In',
    
    # General terms in table empty states etc.
    r'No purchases': 'No records',
    
    # URL names/IDs don't change, just the visible text.
}

count = 0
for filepath in glob.glob('templates/**/*.html', recursive=True):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original = content
    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        count += 1
        print(f"Updated {filepath}")

print(f"Total files updated: {count}")
