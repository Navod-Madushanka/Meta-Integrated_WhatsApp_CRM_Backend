import pathlib

def list_files(startpath):
    path = pathlib.Path(startpath)
    for item in sorted(path.rglob('*')):
        # Skip hidden folders and common junk
        if any(part.startswith('.') or part == '__pycache__' for part in item.parts):
            continue
            
        depth = len(item.relative_to(path).parts)
        spacer = '    ' * (depth - 1)
        print(f'{spacer}├── {item.name}')

list_files('.')