"""
Language Configuration Loader
Loads and validates language configuration profiles from YAML files.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from src.schemas.config import LanguageConfig, LanguageStatus


class ConfigurationError(Exception):
    pass


class LanguageConfigRegistry:
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            # Default to repo root config/languages with robust candidate paths for Vercel
            candidates = [
                Path(__file__).resolve().parent / "languages",
                Path(__file__).resolve().parent.parent.parent / "config" / "languages",
                Path.cwd() / "config" / "languages",
                Path("/var/task") / "config" / "languages",
            ]
            self.config_dir = candidates[0]
            for candidate in candidates:
                if candidate.exists() and any(candidate.glob("*.yaml")):
                    self.config_dir = candidate
                    break
        else:
            self.config_dir = Path(config_dir)

        self._configs: Dict[str, LanguageConfig] = {}
        self.reload()

    def reload(self) -> None:
        """Loads and validates all language configurations, falling back to embedded configs if disk YAMLs are unavailable."""
        configs = {}
        if self.config_dir.exists() and any(self.config_dir.glob("*.yaml")):
            for yaml_file in sorted(self.config_dir.glob("*.yaml")):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        raw_data = yaml.safe_load(f)
                    config = LanguageConfig.model_validate(raw_data)
                    configs[config.language_code] = config
                except Exception as e:
                    raise ConfigurationError(f"Failed to load language config from {yaml_file.name}: {e}") from e
        else:
            # Fallback to pre-compiled embedded configs (ensures 100% serverless runtime reliability)
            from src.config.embedded import EMBEDDED_LANGUAGE_CONFIGS
            for code, raw_data in EMBEDDED_LANGUAGE_CONFIGS.items():
                configs[code] = LanguageConfig.model_validate(raw_data)

        self._configs = configs

    def get(self, language_code: str) -> Optional[LanguageConfig]:
        return self._configs.get(language_code)

    def get_strict(self, language_code: str) -> LanguageConfig:
        config = self.get(language_code)
        if not config:
            raise ConfigurationError(f"Language configuration not found for: {language_code}")
        return config

    def list_all(self) -> List[LanguageConfig]:
        return list(self._configs.values())

    def list_active(self) -> List[LanguageConfig]:
        return [c for c in self._configs.values() if c.status == LanguageStatus.ACTIVE]

    def list_beta(self) -> List[LanguageConfig]:
        return [c for c in self._configs.values() if c.status == LanguageStatus.BETA]
