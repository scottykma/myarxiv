import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.config import get, set, save
from src.profile.generator import generate_interests
from src.profile.fetcher import fetch_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("setup")


def run_setup():
    print("\n" + "=" * 60)
    print("  MyArxiv - Setup Wizard")
    print("=" * 60)

    scholar_url = get("profile.scholar_url", "").strip()

    if not scholar_url:
        print("\nNo Google Scholar URL in config. Entering conversation mode...\n")
        from src.chat.terminal import run_tui
        run_tui()
        return

    print(f"\nUsing Scholar URL from config: {scholar_url}")
    print("Fetching your Google Scholar profile...")
    try:
        profile = fetch_profile(scholar_url)
    except Exception as e:
        print(f"\nFailed to fetch profile: {e}")
        print("Falling back to conversation mode...\n")
        from src.chat.terminal import run_tui
        run_tui()
        return

    print(f"\nProfile found: {profile.name}")
    if profile.affiliation:
        print(f"Affiliation: {profile.affiliation}")
    if profile.interests:
        print(f"Stated interests: {', '.join(profile.interests)}")
    print(f"Recent publications: {len(profile.publications)} found\n")

    if profile.publications:
        print("--- Recent Publications ---")
        for i, pub in enumerate(profile.publications[:10], 1):
            title = pub.get("title", "(no title)")[:80]
            year = pub.get("year", "?")
            cites = pub.get("citation_count", 0)
            print(f"  {i}. [{year}] {title}  (citations: {cites})")

    print("\nAnalyzing your research profile with LLM...")
    try:
        interests = generate_interests(profile)
    except ValueError as e:
        print(f"Error generating interests: {e}")
        print("Please set OPENAI_API_KEY environment variable and try again.")
        sys.exit(1)

    keywords = interests.get("keywords_include", interests.get("keywords", []))
    exclude = interests.get("keywords_exclude", interests.get("exclude_keywords", []))
    categories = interests.get("categories", [])

    print(f"\nGenerated {len(keywords)} keywords (include):")
    for kw in keywords:
        print(f"  \u2022 {kw}")
    if exclude:
        print(f"\nExclude keywords ({len(exclude)}):")
        for kw in exclude:
            print(f"  \u2022 {kw}")
    if categories:
        print(f"\narXiv categories ({len(categories)}):")
        for cat in categories:
            print(f"  \u2022 {cat}")

    set("interests.keywords_include", keywords)
    set("interests.keywords_exclude", exclude)
    set("interests.categories", categories)
    set("profile.name", profile.name)
    set("profile.affiliation", profile.affiliation)
    set("profile.interests", profile.interests)
    set("profile.recent_papers", profile.publications[:20])
    set("user.name", profile.name)
    save()

    print("\nInterests saved to config.yaml")

    refine = input("\nEnter conversation mode to refine interests? (y/n): ").strip().lower()
    if refine in ("y", "yes"):
        from src.chat.terminal import run_tui
        run_tui()

    print("\nSetup complete!")
    print("Run `./update.sh` anytime to adjust your interests.\n")


if __name__ == "__main__":
    run_setup()
