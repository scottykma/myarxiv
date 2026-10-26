import logging

from dotenv import load_dotenv

load_dotenv()

from src.cli import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)


if __name__ == "__main__":
    raise SystemExit(main())
