"""
Script to run PyInstaller with the appropriate options to include
the assets and config directories. This script was necessary since importlib
didn't want to play nice with the assets folder during the build process, and
we wanted to not have to type as much when adding assets.

Part of this script was borrowed from PyInstaller's own data file collection
mechanism with a little bit of tweaking from us to make it work on folders that aren't
necessarily Python packages.
"""
from pathlib import Path
import PyInstaller.__main__
from PyInstaller import compat

def collect_data_files(source_dir, target_dir, recursive = False):
    """
    Collect all non-Python files from source_dir and prepare them for PyInstaller.

    :param source_dir: Directory to search for data files.
    :param target_dir: Target directory inside the executable.
    :return: List of tuples suitable for PyInstaller's --add-data option.
    """
    data_files = []
    excludes = ['**/*' + s for s in compat.ALL_SUFFIXES]
    excludes_len = len(excludes)
    includes = ["**/*"]
    includes_len = len(includes)
    sources = set()
    
    # A helper function to glob the in/ex "cludes", adding a wildcard to refer to all files under a subdirectory if a
    # subdirectory is matched by the first ``clude_len`` patterns. Otherwise, it in/excludes the matched file.
    # **This modifies** ``cludes``. Borrowed from pyinstaller since it does a lot of work for finding data files.
    def clude_walker(
        # Package directory to scan
        pkg_dir,
        # A list of paths relative to ``pkg_dir`` to in/exclude.
        cludes,
        # The number of ``cludes`` for which matching directories should be searched for all files under them.
        clude_len,
        # True if the list is includes, False for excludes.
        is_include
    ):
        for i, c in enumerate(cludes):
            for g in Path(pkg_dir).glob(c):
                if g.is_dir():
                    # Only files are sources. Subdirectories are not.
                    if i < clude_len:
                        # In/exclude all files under a matching subdirectory.
                        cludes.append(str((g / "**/*").relative_to(pkg_dir)))
                else:
                    # In/exclude a matching file.
                    sources.add(g) if is_include else sources.discard(g)

    # Process the package path with clude walker
    clude_walker(source_dir, includes, includes_len, True)
    clude_walker(source_dir, excludes, excludes_len, False)

    # If recursive, process all subdirectories
    if recursive:
        dirs = [source_dir]
        while dirs:
            current_dir = dirs.pop()
            for item in Path(current_dir).iterdir():
                if item.is_dir() and recursive:
                    dirs.append(item)
                    clude_walker(item, includes, includes_len, True)
                    clude_walker(item, excludes, excludes_len, False)

    # Transform the sources into tuples for ``datas``.
    data_files += [(str(s), target_dir) for s in sources]

    return data_files

if __name__ == "__main__":
    pyinstaller_opts = [
        '--onefile',
        '--add-data', 'config:config',
    ]

    # Find the assets during the build and add them to the pyinstaller command
    data_files = collect_data_files("assets", "assets")

    for data_file in data_files:
        pyinstaller_opts.extend(['--add-data', f'{data_file[0]}:{data_file[1]}'])

    pyinstaller_opts.append('talos.py')

    PyInstaller.__main__.run(pyinstaller_opts)