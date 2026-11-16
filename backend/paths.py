"""Resolve runtime paths against the repository, including historical manifests."""
from pathlib import Path, PurePosixPath, PureWindowsPath


def repository_path(root, value):
    root = Path(root).resolve()
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError('Repository path required')
    text = str(value).replace('\\', '/')
    path = Path(value)
    windows = PureWindowsPath(text)
    absolute = PurePosixPath(text).is_absolute() or windows.is_absolute()
    if absolute:
        # A native absolute path already inside this checkout needs no rebasing.
        if path.is_absolute() and path.resolve().is_relative_to(root):
            return path.resolve()
        parts = PurePosixPath(text).parts
        if 'RainbowKTL' not in parts:
            raise ValueError('Absolute path outside repository: ' + text)
        marker = max(i for i, part in enumerate(parts) if part == 'RainbowKTL')
        text = '/'.join(parts[marker + 1:])
    elif windows.drive or text.startswith('/'):
        raise ValueError('Ambiguous repository path: ' + text)
    path = (root / text).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path outside repository: ' + text)
    return path
