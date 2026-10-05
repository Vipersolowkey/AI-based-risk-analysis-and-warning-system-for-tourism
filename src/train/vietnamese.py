"""Shared Vietnamese word segmentation for PhoBERT training and inference."""


def segment_for_phobert(text):
    """PhoBERT expects multi-syllable Vietnamese words joined with underscores."""
    try:
        from pyvi import ViTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "PhoBERT requires PyVi word segmentation. Install requirements-train.txt."
        ) from exc
    return ViTokenizer.tokenize(str(text or ""))
