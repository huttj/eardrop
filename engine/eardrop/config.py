from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _icloud_base() -> Path:
    return Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


@dataclass
class Config:
    # Directories
    watch_dir: Path = field(default_factory=lambda: _icloud_base() / "Eardrop" / "Inbox")
    output_dir: Path = field(default_factory=lambda: _icloud_base() / "Eardrop" / "Transcripts")
    db_path: Path = field(default_factory=lambda: Path.home() / ".local" / "share" / "eardrop" / "eardrop.db")

    # Whisper
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"

    # Ollama
    ollama_model: str = "llama3.1:8b"
    ollama_base_url: str = "http://localhost:11434"

    # HuggingFace (for pyannote)
    hf_token: str | None = None

    # Watcher
    debounce_seconds: float = 3.0
    scan_interval_seconds: float = 60.0

    # Audio extensions to watch
    audio_extensions: frozenset[str] = frozenset({".m4a", ".wav", ".caf", ".mp3", ".ogg", ".flac"})

    def __post_init__(self) -> None:
        # Allow env var overrides
        if v := os.environ.get("EARDROP_WATCH_DIR"):
            self.watch_dir = Path(v)
        if v := os.environ.get("EARDROP_OUTPUT_DIR"):
            self.output_dir = Path(v)
        if v := os.environ.get("EARDROP_DB_PATH"):
            self.db_path = Path(v)
        if v := os.environ.get("EARDROP_WHISPER_MODEL"):
            self.whisper_model = v
        if v := os.environ.get("EARDROP_OLLAMA_MODEL"):
            self.ollama_model = v
        if v := os.environ.get("EARDROP_OLLAMA_BASE_URL"):
            self.ollama_base_url = v
        if v := os.environ.get("EARDROP_HF_TOKEN"):
            self.hf_token = v
        elif not self.hf_token:
            token_path = Path.home() / ".huggingface" / "token"
            if token_path.exists():
                self.hf_token = token_path.read_text().strip()

    def ensure_dirs(self) -> None:
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
