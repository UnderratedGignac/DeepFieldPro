import re
import unidecode
from rapidfuzz import fuzz, process


class NormalizationEngine:
    def __init__(self, alias_dict=None):
        self.alias_dict = alias_dict or {}

    def normalize_name(self, raw_name: str) -> str:
        """
        Normalize player name by removing accents, special chars, and lowercasing.
        Converts spaces to underscores.
        Example: "João Félix" -> "joao_felix", "M. Salah" -> "mohamed_salah"
        """
        # 1. Decode unicode to ascii (accents)
        name = unidecode.unidecode(raw_name)

        # 2. Check alias dictionary first
        if name in self.alias_dict:
            return self.alias_dict[name]

        # 3. Lowercase and strip
        name = name.lower().strip()

        # 4. Remove punctuation (like M. Salah -> m salah)
        name = re.sub(r"[^\w\s]", "", name)

        # 5. Handle initials (e.g., "m salah" to "m_salah" but ideally matched via alias dict or fuzzing downstream)

        # 6. Replace multiple spaces with single space, then to underscore
        name = re.sub(r"\s+", "_", name)

        return name

    def fuzzy_match(
        self, normalized_scraped_name: str, target_names_list: list[str], threshold=92
    ) -> tuple[str, float]:
        """
        Match a scraped normalized name against a known list of valid player names.
        Returns the matched name and the confidence score.
        If below threshold, returns (None, score).
        """
        if not target_names_list:
            return None, 0.0

        best_match, score, _ = process.extractOne(
            normalized_scraped_name, target_names_list, scorer=fuzz.token_sort_ratio
        )

        if score >= threshold:
            return best_match, score
        return None, score


# Singleton instance
normalize_engine = NormalizationEngine()
