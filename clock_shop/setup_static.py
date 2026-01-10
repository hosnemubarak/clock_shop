"""
Script to copy necessary static files from Invoika template.
Run this after installing the project:
    python setup_static.py
"""
import os
import shutil

# Source: Invoika template assets
INVOIKA_ASSETS = os.path.join('..', 'invoika', 'layouts', 'assets')

# Destination: Django static folder
STATIC_DIR = 'static'

# Files/folders to copy
COPY_MAP = {
    'css/bootstrap.min.css': 'css/bootstrap.min.css',
    'css/icons.min.css': 'css/icons.min.css',
    'css/app.min.css': 'css/app.min.css',
    'libs/bootstrap/js/bootstrap.bundle.min.js': 'libs/bootstrap/js/bootstrap.bundle.min.js',
    'libs/simplebar/simplebar.min.js': 'libs/simplebar/simplebar.min.js',
    'fonts': 'fonts',
    'images': 'images',
}

def copy_static_files():
    """Copy static files from Invoika template to Django static folder."""
    
    if not os.path.exists(INVOIKA_ASSETS):
        print(f"Error: Invoika assets not found at {INVOIKA_ASSETS}")
        print("Please ensure the invoika folder is in the parent directory.")
        return False
    
    for src_rel, dest_rel in COPY_MAP.items():
        src_path = os.path.join(INVOIKA_ASSETS, src_rel)
        dest_path = os.path.join(STATIC_DIR, dest_rel)
        
        if not os.path.exists(src_path):
            print(f"Warning: Source not found: {src_path}")
            continue
        
        # Create destination directory if needed
        dest_dir = os.path.dirname(dest_path)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        
        # Copy file or directory
        if os.path.isdir(src_path):
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(src_path, dest_path)
            print(f"Copied directory: {src_rel} -> {dest_rel}")
        else:
            shutil.copy2(src_path, dest_path)
            print(f"Copied file: {src_rel} -> {dest_rel}")
    
    print("\nStatic files setup complete!")
    return True

if __name__ == '__main__':
    copy_static_files()
