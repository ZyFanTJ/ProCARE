import os
import re
import yaml
from typing import Dict, Any, Optional

class Skill:
    def __init__(self, name: str, path: str, metadata: Dict[str, Any], content: str, manager=None):
        self.name = name
        self.path = path
        self.metadata = metadata
        self.content = content
        self.manager = manager
        self._resolved_content = None  # Cache for content with includes resolved

    def _resolve_includes(self, content: str) -> str:
        """
        Resolves {{ include 'path/to/snippet.md' }} directives.
        Path is relative to the skill directory.
        """
        def replace_include(match):
            rel_path = match.group(2).strip()
            abs_path = os.path.join(self.path, rel_path)
            if not os.path.exists(abs_path):
                # Fallback: check if it's relative to global skills dir
                if self.manager:
                    abs_path_global = os.path.join(self.manager.skill_dir, rel_path)
                    if os.path.exists(abs_path_global):
                        abs_path = abs_path_global
                    else:
                        raise FileNotFoundError(f"Include file not found: {rel_path} (searched in {self.path} and {self.manager.skill_dir})")
                else:
                    raise FileNotFoundError(f"Include file not found: {abs_path}")
            
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()

        # Regex for {{ include 'filename' }} or {{ include "filename" }}
        # Support optional spaces
        pattern = r"\{\{\s*include\s+(['\"])(.*?)\1\s*\}\}"
        
        # Iteratively resolve includes to support nested includes
        resolved = content
        max_depth = 5
        current_depth = 0
        while re.search(pattern, resolved) and current_depth < max_depth:
            resolved = re.sub(pattern, replace_include, resolved)
            current_depth += 1
            
        return resolved

    def render(self, **kwargs) -> str:
        """
        Render the skill content (SOP/Prompt) with the provided arguments.
        First resolves includes, then uses standard Python string.format().
        """
        # 1. Resolve includes (with caching)
        if self._resolved_content is None:
            self._resolved_content = self._resolve_includes(self.content)
        
        content_with_includes = self._resolved_content
        
        # 2. Render variables
        try:
            return content_with_includes.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing argument for skill '{self.name}': {e}")
        except ValueError as e:
            # This often happens if there are unescaped braces in the content
            raise ValueError(f"Formatting error in skill '{self.name}'. Check for unescaped braces: {e}")

class SkillManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SkillManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, skill_dir: str = None):
        if hasattr(self, "initialized") and self.initialized:
            return
            
        if skill_dir is None:
            # Default to backend/app/skills
            # Assuming this file is in backend/app/core/
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.skill_dir = os.path.join(base_dir, "skills")
        else:
            self.skill_dir = skill_dir
        
        self._cache: Dict[str, Skill] = {}
        self.initialized = True

    def get_skill(self, name: str) -> Skill:
        if name in self._cache:
            return self._cache[name]
        
        skill_path = os.path.join(self.skill_dir, name, "SKILL.md")
        if not os.path.exists(skill_path):
            raise FileNotFoundError(f"Skill '{name}' not found at {skill_path}")
            
        with open(skill_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
            
        # Parse frontmatter (--- YAML ---)
        # We use a regex to support standard frontmatter syntax
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_content, re.DOTALL)
        if match:
            yaml_block = match.group(1)
            content = match.group(2)
            try:
                metadata = yaml.safe_load(yaml_block)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML metadata in skill '{name}': {e}")
        else:
            metadata = {}
            content = raw_content
            
        skill = Skill(name, os.path.dirname(skill_path), metadata, content, manager=self)
        self._cache[name] = skill
        return skill
