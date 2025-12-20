#!/usr/bin/env python3
"""
Generate a domain-specific dictionary for SymSpell typo correction.

Output: backend/data/domain_dictionary.txt
Format: "word frequency" (space-separated, SymSpell format)
"""

from __future__ import annotations

from pathlib import Path

BASE_VOCABULARY: dict[str, int] = {
    # Instruments (high frequency)
    "piano": 1_000_000,
    "guitar": 1_000_000,
    "violin": 900_000,
    "drums": 800_000,
    "bass": 700_000,
    "cello": 600_000,
    "flute": 600_000,
    "saxophone": 500_000,
    "trumpet": 500_000,
    "clarinet": 400_000,
    "ukulele": 400_000,
    "viola": 300_000,
    "trombone": 300_000,
    "harmonica": 200_000,
    "banjo": 200_000,
    "oboe": 150_000,
    "harp": 150_000,
    "accordion": 100_000,
    "mandolin": 100_000,
    "keyboard": 500_000,
    # Voice/Singing
    "voice": 800_000,
    "vocal": 700_000,
    "vocals": 600_000,
    "singing": 900_000,
    "singer": 500_000,
    # Academic subjects
    "math": 1_000_000,
    "mathematics": 800_000,
    "algebra": 600_000,
    "geometry": 500_000,
    "calculus": 400_000,
    "trigonometry": 300_000,
    "statistics": 400_000,
    "science": 900_000,
    "physics": 600_000,
    "chemistry": 600_000,
    "biology": 600_000,
    "english": 900_000,
    "writing": 800_000,
    "reading": 800_000,
    "grammar": 500_000,
    "essay": 400_000,
    "literature": 400_000,
    "history": 600_000,
    "geography": 400_000,
    # Languages
    "spanish": 800_000,
    "french": 700_000,
    "mandarin": 600_000,
    "chinese": 700_000,
    "japanese": 500_000,
    "german": 500_000,
    "italian": 400_000,
    "korean": 400_000,
    "portuguese": 300_000,
    "russian": 300_000,
    "arabic": 300_000,
    "hindi": 200_000,
    "hebrew": 200_000,
    # Sports/Fitness
    "tennis": 700_000,
    "swimming": 800_000,
    "yoga": 900_000,
    "basketball": 600_000,
    "soccer": 600_000,
    "football": 500_000,
    "golf": 500_000,
    "baseball": 400_000,
    "volleyball": 300_000,
    "boxing": 400_000,
    "martial": 300_000,
    "karate": 300_000,
    "judo": 200_000,
    "taekwondo": 200_000,
    "fencing": 200_000,
    "gymnastics": 400_000,
    "pilates": 500_000,
    "fitness": 600_000,
    "workout": 400_000,
    "training": 500_000,
    # Arts
    "art": 800_000,
    "drawing": 700_000,
    "painting": 600_000,
    "photography": 500_000,
    "dance": 700_000,
    "ballet": 500_000,
    "acting": 400_000,
    "theater": 400_000,
    "theatre": 300_000,
    "drama": 400_000,
    "sculpture": 200_000,
    "pottery": 200_000,
    "ceramics": 200_000,
    # Technology
    "coding": 700_000,
    "programming": 600_000,
    "python": 500_000,
    "javascript": 400_000,
    "computer": 600_000,
    "software": 400_000,
    "web": 500_000,
    "development": 400_000,
    # Common modifiers
    "lessons": 1_000_000,
    "lesson": 900_000,
    "classes": 800_000,
    "class": 700_000,
    "tutor": 900_000,
    "tutoring": 800_000,
    "teacher": 700_000,
    "teaching": 600_000,
    "instructor": 600_000,
    "coach": 700_000,
    "coaching": 600_000,
    "beginner": 800_000,
    "beginners": 700_000,
    "intermediate": 500_000,
    "advanced": 600_000,
    "private": 700_000,
    "group": 500_000,
    "online": 600_000,
    "remote": 400_000,
    "person": 500_000,
    # Audience
    "kids": 900_000,
    "children": 800_000,
    "child": 700_000,
    "adult": 700_000,
    "adults": 600_000,
    "teen": 500_000,
    "teens": 400_000,
    "teenager": 300_000,
    "toddler": 400_000,
    "toddlers": 300_000,
    "senior": 300_000,
    "seniors": 200_000,
    # Time-related
    "morning": 600_000,
    "afternoon": 500_000,
    "evening": 500_000,
    "night": 400_000,
    "weekend": 600_000,
    "weekday": 400_000,
    "weekly": 500_000,
    "daily": 400_000,
    # Price-related
    "cheap": 500_000,
    "affordable": 400_000,
    "budget": 300_000,
    "expensive": 200_000,
    "free": 400_000,
    # NYC Boroughs & Common Areas
    "manhattan": 900_000,
    "brooklyn": 900_000,
    "queens": 700_000,
    "bronx": 600_000,
    "staten": 400_000,
    "island": 300_000,
    "harlem": 500_000,
    "chelsea": 400_000,
    "soho": 400_000,
    "tribeca": 300_000,
    "williamsburg": 400_000,
    "bushwick": 300_000,
    "astoria": 400_000,
    "flushing": 300_000,
}


def generate_dictionary(*, output_path: Path) -> int:
    """Generate the domain dictionary file."""

    sorted_vocab = sorted(BASE_VOCABULARY.items(), key=lambda x: (-x[1], x[0]))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        for word, freq in sorted_vocab:
            handle.write(f"{word} {freq}\n")

    size_kb = output_path.stat().st_size / 1024.0
    print(f"Generated dictionary with {len(sorted_vocab)} words at {output_path}")
    print(f"File size: {size_kb:.1f} KB")
    return len(sorted_vocab)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "backend" / "data" / "domain_dictionary.txt"
    generate_dictionary(output_path=output_path)


if __name__ == "__main__":
    main()
