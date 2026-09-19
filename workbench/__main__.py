import os

import uvicorn


def main():
    # Single worker owns the SQLite queue and crash recovery. No external network binding.
    uvicorn.run(
        "workbench.app:app",
        host="127.0.0.1",
        port=int(os.getenv("WORKBENCH_PORT", "8765")),
        workers=1,
    )


if __name__ == "__main__":
    main()
