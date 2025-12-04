"""Local LLM server for offline summarization.

Provides an OpenAI-compatible API server using llama-cpp-python for
local inference without external API dependencies.

Usage:
    # Start server with a GGUF model
    python -m watercooler_memory.local_server --model /path/to/model.gguf

    # With custom settings
    python -m watercooler_memory.local_server \
        --model /path/to/model.gguf \
        --host 127.0.0.1 \
        --port 8080 \
        --n-ctx 4096

    # Then configure watercooler to use it:
    export LLM_API_BASE=http://localhost:8080/v1
    export LLM_MODEL=local

Requirements:
    pip install watercooler-cloud[local]

Recommended Models (GGUF format):
    - Qwen2.5-3B-Instruct-GGUF (fast, good quality)
    - Phi-3-mini-4k-instruct-GGUF (very fast, smaller)
    - Llama-3.2-3B-Instruct-GGUF (balanced)

Model sources:
    - HuggingFace: https://huggingface.co/models?search=gguf
    - TheBloke collections: https://huggingface.co/TheBloke
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# Default configuration optimized for summarization
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_N_CTX = 4096  # Context window
DEFAULT_N_GPU_LAYERS = -1  # Use all available GPU layers


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
    model_path: str,
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
        FileNotFoundError: If model file doesn't exist.
    """
    if not check_server_dependencies():
        print(
            "Error: llama-cpp-python[server] is required.\n"
            "Install with: pip install 'watercooler-cloud[local]'",
            file=sys.stderr,
        )
        sys.exit(1)

    model_file = Path(model_path).expanduser().resolve()
    if not model_file.exists():
        print(f"Error: Model file not found: {model_file}", file=sys.stderr)
        print(
            "\nDownload a GGUF model from HuggingFace. Recommended for summarization:",
            file=sys.stderr,
        )
        print("  - Qwen2.5-3B-Instruct-GGUF", file=sys.stderr)
        print("  - Phi-3-mini-4k-instruct-GGUF", file=sys.stderr)
        sys.exit(1)

    # Print config hints before starting
    print_config_hint(host, port, model_file.name)

    # Import here to delay ImportError until we've checked
    from llama_cpp.server.app import create_app, Settings

    # Configure server settings
    settings = Settings(
        model=str(model_file),
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
  %(prog)s --model ~/models/qwen2.5-3b-instruct.gguf
  %(prog)s --model ~/models/phi-3-mini.gguf --port 8081 --n-ctx 8192

Recommended models for summarization:
  - Qwen2.5-3B-Instruct-GGUF (fast, good quality)
  - Phi-3-mini-4k-instruct-GGUF (very fast, smaller)
  - Llama-3.2-3B-Instruct-GGUF (balanced)
        """,
    )

    parser.add_argument(
        "--model",
        "-m",
        required=True,
        help="Path to GGUF model file",
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

    start_server(
        model_path=args.model,
        host=args.host,
        port=args.port,
        n_ctx=args.n_ctx,
        n_gpu_layers=args.n_gpu_layers,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
