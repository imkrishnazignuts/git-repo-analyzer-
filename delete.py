import shutil
import time
from pathlib import Path


CLEANUP_INTERVAL_SECONDS = 30 * 60
CLEANUP_DIRECTORIES = [
    Path("repos"),
    Path("chromadb"),
]


def cleanup_directories():
    for directory in CLEANUP_DIRECTORIES:
        if directory.exists():
            shutil.rmtree(directory)

        directory.mkdir(parents=True, exist_ok=True)


def main():
    while True:
        cleanup_directories()
        print(
            f"Cleaned {', '.join(str(path) for path in CLEANUP_DIRECTORIES)}. "
            f"Next cleanup in {CLEANUP_INTERVAL_SECONDS // 60} minutes.",
            flush=True,
        )
        time.sleep(CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
