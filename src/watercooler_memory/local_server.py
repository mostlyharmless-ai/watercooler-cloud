"""Local LLM server for offline summarization.

Provides an OpenAI-compatible API server using llama-cpp-python for
local inference without external API dependencies.

Usage:
    # Start server (auto-downloads default model on first run)
    python -m watercooler_memory.local_server

    # Start with specific model
    python -m watercooler_memory.local_server --model /path/to/model.gguf

    # With custom settings
    python -m watercooler_memory.local_server \
        --host 127.0.0.1 \
        --port 8080 \
        --n-ctx 4096

    # Then configure watercooler to use it:
    export LLM_API_BASE=http://localhost:8080/v1
    export LLM_MODEL=local

Requirements:
    pip install watercooler-cloud[local]

Default Model:
    Qwen2.5-3B-Instruct-GGUF (~2GB) - good quality for summarization

Alternative Models:
    --model-id Qwen/Qwen2.5-1.5B-Instruct-GGUF  (smaller, ~1GB)
    --model-id bartowski/Phi-3-mini-4k-instruct-GGUF  (fast, ~2.3GB)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional


# Default configuration optimized for summarization
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_N_CTX = 4096  # Context window
DEFAULT_N_GPU_LAYERS = -1  # Use all available GPU layers

# Default model for auto-download
# Qwen2.5-3B-Instruct is a good balance of quality and speed for summarization
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-3B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-3b-instruct-q4_k_m.gguf"

# Where to cache downloaded models
DEFAULT_MODELS_DIR = Path.home() / ".watercooler" / "models"


def check_dependencies() -> bool:
    """Check if llama-cpp-python is available."""
    try:
        import llama_cpp  # noqa: F401

        return True
    except ImportError:
        return False


def check_server_dependencies() -> bool:
    """Check if llama-cpp-python[server] is available."""
    try:
        import llama_cpp.server  # noqa: F401

        return True
    except ImportError:
        return False


def check_huggingface_hub() -> bool:
    """Check if huggingface_hub is available."""
    try:
        import huggingface_hub  # noqa: F401

        return True
    except ImportError:
        return False


def get_default_model_path() -> Path:
    """Get path to default model (may not exist yet)."""
    return DEFAULT_MODELS_DIR / DEFAULT_MODEL_FILE


def download_model(
    repo_id: str = DEFAULT_MODEL_REPO,
    filename: str = DEFAULT_MODEL_FILE,
    models_dir: Optional[Path] = None,
    verbose: bool = False,
) -> Path:
    """Download a GGUF model from HuggingFace.

    Args:
        repo_id: HuggingFace repository ID (e.g., "Qwen/Qwen2.5-3B-Instruct-GGUF")
        filename: Specific file to download (e.g., "qwen2.5-3b-instruct-q4_k_m.gguf")
        models_dir: Directory to save models (default: ~/.watercooler/models)
        verbose: Print download progress.

    Returns:
        Path to downloaded model file.

    Raises:
        ImportError: If huggingface_hub is not available.
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

    print(f"Downloading model: {repo_id}/{filename}")
    print(f"This may take a few minutes (~2GB)...")
    print()

    # Download to local models directory
    model_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=models_dir,
    )

    print(f"Model downloaded to: {model_path}")
    return Path(model_path)


def ensure_model(
    model_path: Optional[str] = None,
    model_id: Optional[str] = None,
    verbose: bool = False,
) -> Path:
    """Ensure a model is available, downloading if necessary.

    Args:
        model_path: Explicit path to a GGUF file.
        model_id: HuggingFace model ID to download (e.g., "Qwen/Qwen2.5-3B-Instruct-GGUF")
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
        # Parse repo_id and optional filename
        if ":" in model_id:
            repo_id, filename = model_id.split(":", 1)
        else:
            repo_id = model_id
            # Try to find a Q4_K_M quantized version (good quality/size balance)
            filename = None

        if filename:
            return download_model(repo_id, filename, verbose=verbose)
        else:
            # List files and pick a reasonable default
            if not check_huggingface_hub():
                raise ImportError("huggingface_hub required for model download")

            from huggingface_hub import list_repo_files

            files = list_repo_files(repo_id)
            gguf_files = [f for f in files if f.endswith(".gguf")]

            # Prefer Q4_K_M quantization
            preferred = [f for f in gguf_files if "q4_k_m" in f.lower()]
            if preferred:
                filename = preferred[0]
            elif gguf_files:
                filename = gguf_files[0]
            else:
                print(f"Error: No GGUF files found in {repo_id}", file=sys.stderr)
                sys.exit(1)

            return download_model(repo_id, filename, verbose=verbose)

    # Check for default model
    default_path = get_default_model_path()
    if default_path.exists():
        if verbose:
            print(f"Using cached model: {default_path}")
        return default_path

    # Download default model
    print("No model specified. Downloading default model...")
    print(f"  Repository: {DEFAULT_MODEL_REPO}")
    print(f"  File: {DEFAULT_MODEL_FILE}")
    print()

    return download_model(verbose=verbose)


def print_config_hint(host: str, port: int, model_name: str) -> None:
    """Print configuration hints for using the local server."""
    print("\n" + "=" * 60)
    print("Local LLM Server Configuration")
    print("=" * 60)
    print(f"\nServer running at: http://{host}:{port}/v1")
    print(f"Model: {model_name}")
    print("\nTo use with watercooler memory graph, set these environment variables:")
    print(f"\n  export LLM_API_BASE=http://{host}:{port}/v1")
    print("  export LLM_MODEL=local")
    print("\nOr add to ~/.watercooler/config.toml:")
    print("\n  [memory_graph.llm]")
    print(f'  api_base = "http://{host}:{port}/v1"')
    print('  model = "local"')
    print("\n" + "=" * 60 + "\n")


def start_server(
    model_path: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    n_ctx: int = DEFAULT_N_CTX,
    n_gpu_layers: int = DEFAULT_N_GPU_LAYERS,
    verbose: bool = False,
) -> None:
    """Start the local LLM server.

    Args:
        model_path: Path to GGUF model file.
        host: Host to bind to.
        port: Port to listen on.
        n_ctx: Context window size.
        n_gpu_layers: Number of layers to offload to GPU (-1 = all).
        verbose: Enable verbose output.

    Raises:
        ImportError: If llama-cpp-python[server] is not installed.
    """
    if not check_server_dependencies():
        print(
            "Error: llama-cpp-python[server] is required.\n"
            "Install with: pip install 'watercooler-cloud[local]'",
            file=sys.stderr,
        )
        sys.exit(1)

    # Print config hints before starting
    print_config_hint(host, port, model_path.name)

    # Import here to delay ImportError until we've checked
    from llama_cpp.server.app import create_app, Settings

    # Configure server settings
    settings = Settings(
        model=str(model_path),
        host=host,
        port=port,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        verbose=verbose,
        # Optimized for summarization workloads
        embedding=False,  # Disable embedding endpoint (use separate server)
    )

    # Create and run the app
    app = create_app(settings=settings)

    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info" if verbose else "warning",
    )


def main() -> None:
    """CLI entry point for local server."""
    parser = argparse.ArgumentParser(
        description="Start local LLM server for watercooler summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default model (auto-downloads on first run)
  %(prog)s

  # Use specific local model file
  %(prog)s --model ~/models/qwen2.5-3b-instruct.gguf

  # Download and use a specific HuggingFace model
  %(prog)s --model-id Qwen/Qwen2.5-1.5B-Instruct-GGUF

  # Custom port and context size
  %(prog)s --port 8081 --n-ctx 8192

Available models (--model-id):
  Qwen/Qwen2.5-3B-Instruct-GGUF      (default, ~2GB, good quality)
  Qwen/Qwen2.5-1.5B-Instruct-GGUF    (smaller, ~1GB, faster)
  bartowski/Phi-3-mini-4k-instruct-GGUF  (fast, ~2.3GB)
        """,
    )

    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument(
        "--model",
        "-m",
        help="Path to local GGUF model file",
    )
    model_group.add_argument(
        "--model-id",
        help="HuggingFace model ID to download (e.g., Qwen/Qwen2.5-3B-Instruct-GGUF)",
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
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--n-ctx",
        type=int,
        default=DEFAULT_N_CTX,
        help=f"Context window size (default: {DEFAULT_N_CTX})",
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

    # Ensure model is available (download if needed)
    model_path = ensure_model(
        model_path=args.model,
        model_id=args.model_id,
        verbose=args.verbose,
    )

    start_server(
        model_path=model_path,
        host=args.host,
        port=args.port,
        n_ctx=args.n_ctx,
        n_gpu_layers=args.n_gpu_layers,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
