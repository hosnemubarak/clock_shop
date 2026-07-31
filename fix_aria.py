import os
import re

dirs = ['d:/personal/clock_shop/templates', 'd:/personal/clock_shop/static/js']

patterns = [
    (r'<button type="button" class="btn btn-soft-danger btn-sm" onclick="removeItem\(\$\{item\.index\}\)">', 
     r'<button type="button" aria-label="Remove item" class="btn btn-soft-danger btn-sm" onclick="removeItem(${item.index})">'),
    (r'<button type="button" class="btn btn-sm btn-soft-danger" onclick="removeItem\(\$\{index\}\)">',
     r'<button type="button" aria-label="Remove item" class="btn btn-sm btn-soft-danger" onclick="removeItem(${index})">'),
    (r'<button type="button" class="btn btn-soft-danger btn-sm" onclick="removeItem\(\$\{index\}\)">',
     r'<button type="button" aria-label="Remove item" class="btn btn-soft-danger btn-sm" onclick="removeItem(${index})">')
]

for d in dirs:
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith('.html') or f.endswith('.js'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                original = content
                for pat, rep in patterns:
                    content = re.sub(pat, rep, content)
                
                if original != content:
                    with open(path, 'w', encoding='utf-8') as file:
                        file.write(content)
                    print(f'Updated {path}')
