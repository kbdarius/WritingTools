"""Avoid bundling Babel's 29 MB locale database for the unused Segments backend.

Babel is imported transitively by phonemizer-fork, but Writing Tools uses only
its eSpeak backend for English Kokoro phonemes. No Babel locale lookup occurs.
"""

datas = []
