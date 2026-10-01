from __future__ import annotations
import re
from typing import Any
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))

class IncidentRetriever:
    """Hybrid retriever: word/character TF-IDF similarity plus lexical overlap.
    TF-IDF is a lightweight local baseline; replace/augment with embeddings for production."""
    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True).copy()
        corpus = self.df["search_text"].fillna("").astype(str).tolist()
        self.word_vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=120000, sublinear_tf=True)
        self.char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=120000, sublinear_tf=True)
        self.word_matrix = self.word_vectorizer.fit_transform(corpus)
        self.char_matrix = self.char_vectorizer.fit_transform(corpus)
        # Corpus-local latent semantic embeddings: no network or API key is required.
        components = min(128, max(1, self.word_matrix.shape[0] - 1), max(1, self.word_matrix.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=components, random_state=17) if self.word_matrix.shape[1] > 1 and self.word_matrix.shape[0] > 1 else None
        self.embedding_matrix = normalize(self.svd.fit_transform(self.word_matrix)) if self.svd else None
        self.doc_tokens = [_tokens(t) for t in corpus]

    def search(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        filters = filters or {}
        q_word = self.word_vectorizer.transform([query])
        q_char = self.char_vectorizer.transform([query])
        word_scores = cosine_similarity(q_word, self.word_matrix).ravel()
        char_scores = cosine_similarity(q_char, self.char_matrix).ravel()
        semantic_scores = np.zeros(len(self.df))
        if self.svd:
            q_embedding = normalize(self.svd.transform(q_word))
            semantic_scores = cosine_similarity(q_embedding, self.embedding_matrix).ravel()
        qt = _tokens(query)
        lexical = np.array([
            len(qt & dt) / max(1, len(qt | dt)) for dt in self.doc_tokens
        ])
        # Balanced hybrid score, normalized to [0,1].
        # Lexical exactness leads; latent vectors contribute a smaller semantic rerank.
        scores = 0.53 * word_scores + 0.24 * char_scores + 0.18 * lexical + 0.05 * semantic_scores

        eligible = np.ones(len(self.df), dtype=bool)
        for field, expected in filters.items():
            if expected is None or str(expected).strip() == "":
                continue
            if field not in self.df.columns:
                continue
            vals = self.df[field].astype(str).str.lower().str.strip().to_numpy()
            expected_values = expected if isinstance(expected, list) else [expected]
            expected_values = [str(x).lower().strip() for x in expected_values]
            eligible &= np.isin(vals, expected_values)
        indexes = np.where(eligible)[0]
        indexes = sorted(indexes, key=lambda i: float(scores[i]), reverse=True)[:max(1, min(int(top_k), 50))]
        results = []
        for rank, i in enumerate(indexes, start=1):
            row = self.df.iloc[i].to_dict()
            row["rank"] = rank
            row["score"] = round(float(scores[i]), 4)
            # Keep API response clean and JSON serializable.
            results.append({k: (None if pd.isna(v) else str(v) if not isinstance(v, (int, float, bool)) else v)
                            for k, v in row.items() if k != "search_text"})
        return results
