"""Retrieval-augmented file selection.

Splits source files into AST-level chunks (functions, methods, classes, module-level),
embeds them via OpenAI, builds a FAISS index, and queries for the most relevant chunks
given an issue description. The files those chunks come from are what gets sent to
the LLM — not the whole codebase.
"""

import ast
from dataclasses import dataclass

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from openai import OpenAI


EMBED_MODEL = "text-embedding-3-small"


@dataclass
class Chunk:
    file_path: str
    kind: str        # "function", "class", "method", "module", "file"
    name: str        # e.g. "Job.__lt__" or "<module>"
    code: str

    def for_embedding(self) -> str:
        """Format this chunk for embedding — include a one-line header for context."""
        return f"{self.kind} {self.name} in {self.file_path}\n{self.code}"


def chunk_python_file(file_path: str, content: str) -> list[Chunk]:
    """Split a Python file into AST-aware chunks.

    Falls back to a single 'file' chunk if the source doesn't parse.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [Chunk(file_path, "file", "<file>", content)]

    lines = content.split("\n")
    chunks: list[Chunk] = []
    used_lines: set[int] = set()

    def add_chunk(node, kind: str, name: str) -> None:
        start = node.lineno - 1
        end = node.end_lineno or (start + 1)
        chunk_code = "\n".join(lines[start:end])
        chunks.append(Chunk(file_path, kind, name, chunk_code))
        used_lines.update(range(start, end))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_chunk(node, "function", node.name)
        elif isinstance(node, ast.ClassDef):
            add_chunk(node, "class", node.name)
            # Also chunk methods individually for finer retrieval.
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_chunk(child, "method", f"{node.name}.{child.name}")

    # Anything that's neither in a function nor a class — imports, constants, etc.
    module_lines = [lines[i] for i in range(len(lines)) if i not in used_lines]
    module_code = "\n".join(module_lines).strip()
    if module_code:
        chunks.append(Chunk(file_path, "module", "<module>", module_code))

    return chunks


def chunk_repo(files: dict[str, str]) -> list[Chunk]:
    """Chunk every file in the repo. Returns one flat list of chunks."""
    all_chunks: list[Chunk] = []
    for file_path, content in files.items():
        all_chunks.extend(chunk_python_file(file_path, content))
    return all_chunks


def embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    """Embed a batch of strings via OpenAI. Returns an (N, D) float32 array."""
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    vectors = [item.embedding for item in response.data]
    return np.array(vectors, dtype=np.float32)


def build_index(embeddings: np.ndarray):
    """Build a FAISS inner-product index. L2-normalize so IP == cosine similarity."""
    if faiss is None:
        raise ImportError("faiss-cpu not installed. Run: pip install faiss-cpu")
    arr = embeddings.copy()
    faiss.normalize_L2(arr)
    index = faiss.IndexFlatIP(arr.shape[1])
    index.add(arr)
    return index


def query_index(
    client: OpenAI,
    index,
    chunks: list[Chunk],
    query_text: str,
    top_k: int,
) -> list[Chunk]:
    """Find the top-K most relevant chunks for a query."""
    query_vec = embed_texts(client, [query_text])
    faiss.normalize_L2(query_vec)
    _, indices = index.search(query_vec, min(top_k, len(chunks)))
    return [chunks[i] for i in indices[0]]


def select_relevant_files(
    client: OpenAI,
    files: dict[str, str],
    query_text: str,
    top_k: int = 5,
) -> tuple[dict[str, str], list[Chunk]]:
    """Run the full retrieval pipeline.

    Returns (relevant_files, top_chunks):
      - relevant_files: subset of `files` whose chunks ranked in the top-K
      - top_chunks: the top-K chunks themselves, for logging
    """
    chunks = chunk_repo(files)
    if not chunks:
        return files, []

    chunk_texts = [c.for_embedding() for c in chunks]
    embeddings = embed_texts(client, chunk_texts)
    index = build_index(embeddings)
    top_chunks = query_index(client, index, chunks, query_text, top_k)

    relevant_paths = {c.file_path for c in top_chunks}
    relevant_files = {p: files[p] for p in relevant_paths if p in files}

    return relevant_files, top_chunks