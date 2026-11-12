"""Process source inventory. Data roots, configuration and credentials are excluded."""
import hashlib
import json
import os
from pathlib import Path


class RuntimeBuild:
    def __init__(self, backend_directory):
        self.directory = Path(backend_directory).resolve()
        self.startup = self.capture()
        self.build_id = self.identity(self.startup)

    @staticmethod
    def identity(files):
        encoded = json.dumps(files, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def capture(self):
        files = {}
        if not self.directory.is_dir():
            return files
        def unreadable(error):
            files['@unreadable'] = None
        def linked(path):
            return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())
        for folder, directories, names in os.walk(self.directory, followlinks=False, onerror=unreadable):
            parent = Path(folder)
            for name in directories[:]:
                path = parent / name
                if name == '__pycache__':
                    directories.remove(name)
                elif linked(path):
                    files['@link/' + path.relative_to(self.directory).as_posix()] = None
                    directories.remove(name)
            for name in names:
                path = parent / name
                if path.suffix != '.py':
                    continue
                if linked(path):
                    # Never read a link destination; an external source cannot silently evade the inventory.
                    files['@link/' + path.relative_to(self.directory).as_posix()] = None
                else:
                    try:
                        files[path.relative_to(self.directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
                    except OSError:
                        files[path.relative_to(self.directory).as_posix()] = None
        return files

    def status(self):
        current = self.capture()
        removed = sorted(set(self.startup) - set(current))
        added = sorted(set(current) - set(self.startup))
        changed = sorted(name for name in set(current) & set(self.startup)
                         if current[name] != self.startup[name] or current[name] is None)
        ready = bool(self.startup) and not (removed or added or changed) and all(self.startup.values())
        return dict(schema_version=1, build_id=self.build_id, source_current=ready,
                    status='CURRENT' if ready else 'RESTART_REQUIRED',
                    changed_source_files=changed, added_source_files=added, removed_source_files=removed,
                    current_source_sha256=current)
