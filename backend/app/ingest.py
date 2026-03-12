# backend/app/ingest.py

import re
import json
import time
import hashlib
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

import wikipediaapi
from tqdm import tqdm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, list[str]] = {
    "space": [
        "Black hole", "Milky Way", "Mars", "International Space Station",
        "James Webb Space Telescope", "Neutron star", "Solar wind",
        "Hubble Space Telescope", "Apollo 11", "Exoplanet",
        "Dark matter", "Supernova", "Saturn", "Jupiter", "Asteroid belt",
        "Spacecraft", "Cosmology", "Big Bang", "Pulsar", "Quasar",
    ],
    "medicine": [
        "Vaccine", "Antibiotic", "Cancer", "Diabetes", "Human brain",
        "Immune system", "Organ transplantation", "Surgery", "Virus",
        "Pandemic", "DNA", "Gene therapy", "Stem cell", "Neuroscience",
        "Cardiology", "Epidemiology", "Pharmacology", "Mental health",
        "Alzheimer's disease", "CRISPR",
    ],
    "technology": [
        "Artificial intelligence", "Internet", "Semiconductor",
        "Quantum computing", "Blockchain", "Machine learning",
        "Computer vision", "Robotics", "Cloud computing", "Cybersecurity",
        "5G", "Electric vehicle", "Renewable energy", "Nanotechnology",
        "3D printing", "Augmented reality", "Bitcoin", "Autonomous vehicle",
        "Natural language processing", "Neural network",
    ],
    "science": [
        "Photosynthesis", "Evolution", "Relativity", "Thermodynamics",
        "Quantum mechanics", "Periodic table", "Electromagnetic radiation",
        "Cell biology", "Plate tectonics", "Nuclear fusion",
        "Climate change", "Ecology", "Genetics", "Atomic theory",
        "Fluid dynamics", "Chemical bond", "Entropy", "Radioactivity",
        "Taxonomy", "Biochemistry",
    ],
    "history": [
        "World War II", "Roman Empire", "French Revolution",
        "Industrial Revolution", "Cold War", "Ancient Egypt",
        "Mongol Empire", "Renaissance", "American Civil War",
        "Age of Exploration", "Byzantine Empire", "Ottoman Empire",
        "Great Wall of China", "Silk Road", "Black Death",
        "World War I", "Cuban Missile Crisis", "Colonialism",
        "Enlightenment", "Feudalism",
    ],
    "geography": [
        "Amazon River", "Sahara", "Himalayas", "Pacific Ocean",
        "Amazon rainforest", "Nile", "Atacama Desert", "Great Barrier Reef",
        "Mount Everest", "Mediterranean Sea", "Gobi Desert",
        "Andes", "Congo River", "Arctic Ocean", "Patagonia",
        "Tibetan Plateau", "Great Rift Valley", "Mekong", "Danube",
        "Mariana Trench",
    ],
    "economics": [
        "Capitalism", "Gross domestic product", "Inflation",
        "Stock market", "Supply and demand", "Central bank",
        "International trade", "Unemployment", "Fiscal policy",
        "Monetary policy", "Globalization", "Microeconomics",
        "Macroeconomics", "Free trade", "Keynesian economics",
        "Cryptocurrency", "Foreign exchange market", "Public debt",
        "Economic inequality", "World Bank",
    ],
    "sports": [
        "Football", "Olympics", "Tennis", "Basketball", "Cricket",
        "Formula One", "Swimming", "Athletics", "Rugby union", "Golf",
        "Boxing", "Cycling", "Baseball", "Volleyball", "Table tennis",
        "Ice hockey", "Skiing", "Triathlon", "Rowing", "Gymnastics",
    ],
    "culture": [
        "Philosophy", "Literature", "Classical music", "Film",
        "Architecture", "Painting", "Theatre", "Dance", "Mythology",
        "Religion", "Language", "Folklore", "Cuisine", "Fashion",
        "Photography", "Sculpture", "Opera", "Anime", "Jazz", "Hip hop",
    ],
    "nature": [
        "Biodiversity", "Photosynthesis", "Migration", "Coral reef",
        "Rainforest", "Endangered species", "Symbiosis", "Predation",
        "Animal communication", "Pollination", "Wetland", "Mangrove",
        "Tundra", "Savanna", "Deep sea", "Bird", "Mammal",
        "Insect", "Marine biology", "Fungus",
    ],
    "society": [
        "Democracy", "Human rights", "Education", "Poverty",
        "Immigration", "Feminism", "Urbanization", "Social media",
        "Public health", "Journalism", "Law", "Taxation",
        "Nonprofit organization", "Civil society", "Voting",
        "Welfare state", "Discrimination", "Social mobility",
        "Community", "Bureaucracy",
    ],
    "general": [
        "Knowledge", "Communication", "Leadership", "Creativity",
        "Decision-making", "Ethics", "Logic", "Memory", "Learning",
        "Motivation", "Consciousness", "Intelligence", "Emotion",
        "Perception", "Reasoning", "Problem solving", "Innovation",
        "Collaboration", "Identity", "Time",
    ],
}

ARTICLE_LIMIT   = 20
MAX_CHARS       = 3000
REQUEST_DELAY   = 0.05
OUTPUT_FILENAME = "docs.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc_id(index: int, title: str) -> str:
    digest = hashlib.md5(title.encode()).hexdigest()[:8]
    return f"doc_{index:04d}_{digest}"


def _clean_text(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw)
    text = re.sub(r"==+[^=]+=+", "", text)          # remove section headers
    text = re.sub(r"\[\d+\]", "", text)              # remove citation markers
    text = re.sub(r"[^\x00-\x7F]+", " ", text)      # strip non-ASCII
    return text.strip()[:MAX_CHARS]


def _make_snippet(text: str, length: int = 200) -> str:
    return text[:length].rsplit(" ", 1)[0] + "…" if len(text) > length else text


def _wiki_source_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_wikipedia_docs(
    limit_per_category: int = ARTICLE_LIMIT,
    category_filter: dict[str, list[str]] | None = None,
) -> list[dict]:
    wiki = wikipediaapi.Wikipedia(
        language="en",
        user_agent="hybrid-search-engine/1.0 (academic assignment)"
    )

    source = category_filter if category_filter is not None else CATEGORIES
    docs: list[dict] = []
    index = 1

    for category, titles in source.items():
        fetched = 0
        for title in titles:
            if fetched >= limit_per_category:
                break
            # ... rest of loop unchanged
            page = wiki.page(title)
            time.sleep(REQUEST_DELAY)

            if not page.exists():
                logger.warning("Page not found: %s", title)
                continue

            raw = page.text
            if not raw.strip():
                logger.warning("Empty page: %s", title)
                continue

            text = _clean_text(raw)
            doc = {
                "doc_id":     _make_doc_id(index, title),
                "title":      page.title,
                "text":       text,
                "snippet":    _make_snippet(text),
                "source":     _wiki_source_url(page.title),
                "category":   category,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            docs.append(doc)
            index += 1
            fetched += 1

    return docs

def run_ingest(
    input_dir:  Path,
    output_dir: Path,
    categories: list[str] | None = None,   # None = fetch all
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME

    # Filter CATEGORIES dict if caller specified a subset
    target = (
        {k: CATEGORIES[k] for k in categories if k in CATEGORIES}
        if categories
        else CATEGORIES
    )

    if not target:
        logger.warning(
            "No valid categories matched %s — falling back to all.", categories
        )
        target = CATEGORIES

    logger.info(
        "Fetching Wikipedia articles for %d categories: %s…",
        len(target), list(target.keys()),
    )
    wiki_docs = fetch_wikipedia_docs(category_filter=target)
    logger.info("Fetched %d Wikipedia docs", len(wiki_docs))

    txt_docs = load_txt_docs(input_dir, start_index=len(wiki_docs) + 1)
    if txt_docs:
        logger.info("Loaded %d .txt docs from %s", len(txt_docs), input_dir)

    all_docs = wiki_docs + txt_docs
    written  = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for doc in tqdm(all_docs, desc="Writing JSONL"):
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
            written += 1

    logger.info("Wrote %d docs → %s", written, output_path)
    return written

def load_txt_docs(input_dir: Path, start_index: int) -> list[dict]:
    docs: list[dict] = []
    txt_files = sorted(input_dir.glob("*.txt"))

    if not txt_files:
        return docs

    for i, path in enumerate(txt_files, start=start_index):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        text = _clean_text(raw)
        if not text:
            logger.warning("Empty .txt file: %s", path.name)
            continue

        title = path.stem.replace("_", " ").title()
        doc = {
            "doc_id":     _make_doc_id(i, title),
            "title":      title,
            "text":       text,
            "snippet":    _make_snippet(text),
            "source":     path.name,
            "category":   "general",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        docs.append(doc)

    return docs


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Ingest docs into JSONL")
    parser.add_argument(
        "--input", type=Path, default=Path("data/raw"),
        help="Folder scanned for .txt files (default: data/raw)"
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/processed"),
        help="Output folder for docs.jsonl (default: data/processed)"
    )
    args = parser.parse_args()

    total = run_ingest(args.input, args.out)
    print(f"\n✓ Ingest complete — {total} documents written")


if __name__ == "__main__":
    main()