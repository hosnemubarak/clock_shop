import os
import re

APPS = ['core', 'customers', 'inventory', 'sales', 'warehouse', 'reports']
BASE_DIR = r'd:\personal\clock_shop'

url_map = {}

for app in APPS:
    urls_file = os.path.join(BASE_DIR, 'apps', app, 'urls.py')
    if os.path.exists(urls_file):
        with open(urls_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'app_name =' not in content:
                content = content.replace('urlpatterns = [', f"app_name = '{app}'\n\nurlpatterns = [")
                with open(urls_file, 'w', encoding='utf-8') as fw:
                    fw.write(content)
            
            names = re.findall(r"name=['\"]([^'\"]+)['\"]", content)
            for name in names:
                url_map[name] = app

print('Found URL names:', len(url_map))
print(url_map)

# Update templates
templates_dir = os.path.join(BASE_DIR, 'templates')
for root, _, files in os.walk(templates_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            for url_name, app_name in url_map.items():
                # Replace {% url 'name' ... %} but prevent double namespace {% url 'app:app:name' ... %}
                # We can match exactly the space before and the quote
                
                # Double quotes match: {% url "name"
                pattern_double = rf'\{{%\s*url\s+"{url_name}"'
                replacement_double = f'{{% url "{app_name}:{url_name}"'
                new_content = re.sub(pattern_double, replacement_double, new_content)
                
                # Single quotes match: {% url 'name'
                pattern_single = rf"\{{%\s*url\s+'{url_name}'"
                replacement_single = f"{{% url '{app_name}:{url_name}'"
                new_content = re.sub(pattern_single, replacement_single, new_content)
                
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as fw:
                    fw.write(new_content)
                print(f'Updated {file}')

# Update views
for app in APPS:
    views_file = os.path.join(BASE_DIR, 'apps', app, 'views.py')
    if os.path.exists(views_file):
        with open(views_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        new_content = content
        for url_name, app_name in url_map.items():
            pattern1 = rf"reverse\('{url_name}'"
            replacement1 = f"reverse('{app_name}:{url_name}'"
            new_content = re.sub(pattern1, replacement1, new_content)
            
            pattern2 = rf'reverse\("{url_name}"'
            replacement2 = f'reverse("{app_name}:{url_name}"'
            new_content = re.sub(pattern2, replacement2, new_content)
            
            pattern3 = rf"redirect\('{url_name}'"
            replacement3 = f"redirect('{app_name}:{url_name}'"
            new_content = re.sub(pattern3, replacement3, new_content)
            
            pattern4 = rf'redirect\("{url_name}"'
            replacement4 = f'redirect("{app_name}:{url_name}"'
            new_content = re.sub(pattern4, replacement4, new_content)
            
            pattern5 = rf"reverse_lazy\('{url_name}'"
            replacement5 = f"reverse_lazy('{app_name}:{url_name}'"
            new_content = re.sub(pattern5, replacement5, new_content)
            
            pattern6 = rf'reverse_lazy\("{url_name}"'
            replacement6 = f'reverse_lazy("{app_name}:{url_name}"'
            new_content = re.sub(pattern6, replacement6, new_content)
            
        if new_content != content:
            with open(views_file, 'w', encoding='utf-8') as fw:
                fw.write(new_content)
            print(f'Updated {app}/views.py')
