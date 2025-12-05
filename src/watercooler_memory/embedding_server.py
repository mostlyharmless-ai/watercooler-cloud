"""Local embedding server for vector embeddings.

Provides an OpenAI-compatible API server using llama-cpp-python for
local embedding generation without external API dependencies.

Runs on port 8080 by default (separate from summarization on port 8000).

Usage:
    # Start server (auto-downloads default model on first run)
    python -m watercooler_memory.embedding_server

    # Start with specific model
    python -m watercooler_memory.embedding_server --model /path/to/model.gguf

    # With custom settings
    python -m watercooler_memory.embedding_server \
        --host 127.0.0.1 \
        --port 8080

    # Then configure watercooler to use it:
    export EMBEDDING_API_BASE=http://localhost:8080/v1
    export EMBEDDING_MODEL=bge-m3

Requirements:
    pip install watercooler-cloud[local]

Default Model:
    bge-m3-GGUF (~2GB) - state-of-the-art embedding quality
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .local_server import (
    DEFAULT_HOST,
    DEFAULT_MODELS_DIR,
    DEFAULT_N_GPU_LAYERS,
    check_huggingface_hub,
    check_server_dependencies,
)


# Default configuration for embedding server
DEFAULT_EMBEDDING_PORT = 8080
DEFAULT_EMBEDDING_N_CTX = 512  # Embeddings need less context than chat

# Default embedding model
DEFAULT_EMBEDDING_MODEL_REPO = "KimChen/bge-m3-GGUF"
DEFAULT_EMBEDDING_MODEL_FILE = "bge-m3-q8_0.gguf"


def get_default_embedding_model_path() -> Path:
    """Get path to default embedding model (may not exist yet)."""
    return DEFAULT_MODELS_DIR / DEFAULT_EMBEDDING_MODEL_FILE


def download_embedding_model(
    repo_id: str = DEFAULT_EMBEDDING_MODEL_REPO,
    filename: str = DEFAULT_EMBEDDING_MODEL_FILE,
    models_dir: Optional[Path] = None,
    verbose: bool = False,
) -> Path:
    """Download embedding model from HuggingFace.

    Args:
        repo_id: HuggingFace repository ID
        filename: Specific file to download
        models_dir: Directory to save models (default: ~/.watercooler/models)
        verbose: Print download progress.

    Returns:
        Path to downloaded model file.
    """
    if not check_huggingface_hub():
        raise ImportError(
            "huggingface_hub is required for model download.\n"
            "Install with: pip install 'watercooler-cloud[local]'"
        )

    from huggingface_hub import hf_hub_download

    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR

    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading embedding model: {repo_id}/{filename}")
    print("This may take a few minutes (~2GB)...")
    print()

    model_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=models_dir,
    )

    print(f"Model downloaded to: {model_path}")
    return Path(model_path)


def ensure_embedding_model(
    model_path: Optional[str] = None,
    model_id: Optional[str] = None,
    verbose: bool = False,
) -> Path:
    """Ensure embedding model is available, downloading if necessary.

    Args:
        model_path: Explicit path to a GGUF file.
        model_id: HuggingFace model ID to download
        verbose: Print progress messages.

    Returns:
        Path to the model file.
    """
    # If explicit path provided, use it
    if model_path:
        path = Path(model_path).expanduser().resolve()
        if not path.exists():
            print(f"Error: Model file not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path

    # If model_id provided, download from HuggingFace
    if model_id:
        if ":" in model_id:
            repo_id, filename = model_id.split(":", 1)
        else:
            repo_id = model_id
            filename = None

        if filename:
            return download_embedding_model(repo_id, filename, verbose=verbose)
        else:
            # List files and pick a reasonable default
            if not check_huggingface_hub():
                raise ImportError("huggingface_hub required for model download")

            from huggingface_hub import list_repo_files

            files = list_repo_files(repo_id)
            gguf_files = [f for f in files if f.endswith(".gguf")]

            # Prefer Q8_0 quantization for embeddings (higher quality)
            preferred = [f for f in gguf_files if "q8_0" in f.lower()]
            if preferred:
                filename = preferred[0]
            elif gguf_files:
                filename = gguf_files[0]
            else:
                print(f"Error: No GGUF files found in {repo_id}", file=sys.stderr)
                sys.exit(1)

            return download_embedding_model(repo_id, filename, verbose=verbose)

    # Check for default model
    default_path = get_default_embedding_model_path()
    if default_path.exists():
        if verbose:
            print(f"Using cached embedding model: {default_path}")
        return default_path

    # Download default model
    print("No embedding model specified. Downloading default model...")
    print(f"  Repository: {DEFAULT_EMBEDDING_MODEL_REPO}")
    print(f"  File: {DEFAULT_EMBEDDING_MODEL_FILE}")
    print()

    return download_embedding_model(verbose=verbose)


def print_embedding_config_hint(host: str, port: int, model_name: str) -> None:
    """Print configuration hints for using the embedding server."""
    print("\n" + "=" * 60)
    print("Local Embedding Server Configuration")
    print("=" * 60)
    print(f"\nServer running at: http://{host}:{port}/v1")
    print(f"Model: {model_name}")
    print("\nTo use with watercooler memory graph, set these environment variables:")
    print(f"\n  export EMBEDDING_API_BASE=http://{host}:{port}/v1")
    print("  export EMBEDDING_MODEL=bge-m3")
    print("\nOr add to ~/.watercooler/config.toml:")
    print("\n  [memory_graph.embedding]")
    print(f'  api_base = "http://{host}:{port}/v1"')
    print('  model = "bge-m3"')
    print("\n" + "=" * 60 + "\n")


def start_embedding_server(
    model_path: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_EMBEDDING_PORT,
    n_ctx: int = DEFAULT_EMBEDDING_N_CTX,
    n_gpu_layers: int = DEFAULT_N_GPU_LAYERS,
    verbose: bool = False,
) -> None:
    """Start the local embedding server.

    Args:
        model_path: Path to GGUF model file.
        host: Host to bind to.
        port: Port to listen on.
        n_ctx: Context window size.
        n_gpu_layers: Number of layers to offload to GPU (-1 = all).
        verbose: Enable verbose output.
    """
    if not check_server_dependencies():
        print(
            "Error: llama-cpp-python[server] is required.\n"
            "Install with: pip install 'watercooler-cloud[local]'",
            file=sys.stderr,
        )
        sys.exit(1)

    print_embedding_config_hint(host, port, model_path.name)

    from llama_cpp.server.app import create_app, Settings

    settings = Settings(
        model=str(model_path),
        host=host,
        port=port,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        verbose=verbose,
        embedding=True,  # Enable embedding endpoint
    )

    app = create_app(settings=settings)

    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info" if verbose else "warning",
    )


def main() -> None:
    """CLI entry point for embedding server."""
    parser = argparse.ArgumentParser(
        description="Start local embedding server for watercooler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default model (auto-downloads on first run)
  %(prog)s

  # Use specific local model file
  %(prog)s --model ~/models/bge-m3-q8_0.gguf

  # Download and use a specific HuggingFace model
  %(prog)s --model-id KimChen/bge-m3-GGUF:Q8_0

  # Custom port
  %(prog)s --port 8081

Available models (--model-id):
  KimChen/bge-m3-GGUF         (default, ~2GB, state-of-the-art)
  nomic-ai/nomic-embed-text-v1.5-GGUF  (lighter, ~550MB)
        """,
    )

    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument(
        "--model",
        "-m",
        help="Path to local GGUF embedding model file",
    )
    model_group.add_argument(
        "--model-id",
        help="HuggingFace model ID to download (e.g., KimChen/bge-m3-GGUF)",
    )

    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host to bind to (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=DEFAULT_EMBEDDING_PORT,
        help=f"Port to listen on (default: {DEFAULT_EMBEDDING_PORT})",
    )
    parser.add_argument(
        "--n-ctx",
        type=int,
        default=DEFAULT_EMBEDDING_N_CTX,
        help=f"Context window size (default: {DEFAULT_EMBEDDING_N_CTX})",
    )
    parser.add_argument(
        "--n-gpu-layers",
        type=int,
        default=DEFAULT_N_GPU_LAYERS,
        help="GPU layers to offload (-1 = all, 0 = CPU only)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    model_path = ensure_embedding_model(
        model_path=args.model,
        model_id=args.model_id,
        verbose=args.verbose,
    )

    start_embedding_server(
        model_path=model_path,
        host=args.host,
        port=args.port,
        n_ctx=args.n_ctx,
        n_gpu_layers=args.n_gpu_layers,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
