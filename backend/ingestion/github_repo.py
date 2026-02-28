import os
import shutil
import stat
import tempfile
from typing import List
from git import Repo
from backend.ingestion.base import BaseIngester, Chunk
from backend.ingestion.text import TextIngester
from backend.ingestion.code import CodeIngester, SUPPORTED_EXTENSIONS
from backend.config import CHUNKING, SOURCES


class GitHubRepoIngester(BaseIngester):
    def __init__(self):
        self.clone_dir = SOURCES["github_clone_dir"]
        self.max_file_size_kb = SOURCES["max_file_size_mb"] * 1024
        self.chunk_size = CHUNKING["github"]["size"]
        self.overlap = CHUNKING["github"]["overlap"]
        
        # Directories and files to exclude
        self.exclude_dirs = {
            "node_modules", ".git", "dist", "build", "__pycache__",
            ".venv", "venv", "env", ".env", "target", "bin", "obj",
            "vendor", "third_party", ".idea", ".vscode"
        }
        self.exclude_patterns = {".lock", ".min.js", ".min.css", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "Cargo.lock", "poetry.lock"}

    def _safe_rmtree(self, path: str):
        """Robustly delete a directory tree on Windows where files may be read-only."""

        def _onerror(func, p, exc_info):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except Exception:
                raise

        shutil.rmtree(path, onerror=_onerror)

    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest a GitHub repository from URL."""
        chunks = []
        
        # Parse repo URL
        repo_url = source_path
        repo_name = self._extract_repo_name(repo_url)
        
        if not repo_name:
            return chunks
        
        # Create clone directory
        os.makedirs(self.clone_dir, exist_ok=True)
        clone_path = tempfile.mkdtemp(prefix=f"{repo_name}_", dir=self.clone_dir)
        
        try:
            # Shallow clone
            Repo.clone_from(repo_url, clone_path, depth=1)
            
            # Process files
            chunks = self._process_repo(clone_path, repo_url, repo_name)
            
        except Exception as e:
            print(f"Error cloning repository: {e}")
        
        finally:
            # Clean up clone directory
            if os.path.exists(clone_path):
                try:
                    self._safe_rmtree(clone_path)
                except Exception as e:
                    print(f"Error cleaning up cloned repository: {e}")
        
        return chunks

    def _extract_repo_name(self, url: str) -> str:
        """Extract repository name from URL."""
        # Handle various GitHub URL formats
        # https://github.com/user/repo
        # git@github.com:user/repo.git
        url = url.rstrip("/")
        
        if url.endswith(".git"):
            url = url[:-4]
        
        parts = url.split("/")
        if len(parts) >= 2:
            return parts[-1]
        
        return None

    def _process_repo(self, repo_path: str, repo_url: str, repo_name: str) -> List[Chunk]:
        """Process all files in the repository."""
        chunks = []
        
        for root, dirs, files in os.walk(repo_path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for filename in files:
                file_path = os.path.join(root, filename)
                
                # Check file size
                if os.path.getsize(file_path) > self.max_file_size_kb * 1024:
                    continue
                
                # Check exclude patterns
                if any(p in filename.lower() for p in self.exclude_patterns):
                    continue
                
                # Get relative path from repo root
                rel_path = os.path.relpath(file_path, repo_path)
                
                # Process based on file type
                ext = os.path.splitext(filename)[1].lower()
                
                file_chunks = []
                if filename.lower().endswith(('.md', '.txt')):
                    # Process markdown and text files
                    file_chunks = self._process_readme(file_path, repo_url, rel_path)
                    chunks.extend(file_chunks)
                    print(f"[DEBUG] Embedded text file: {rel_path} ({len(file_chunks)} chunks)")
                
                elif ext in SUPPORTED_EXTENSIONS:
                    # Process as code
                    file_chunks = self._process_code_file(file_path, repo_url, rel_path)
                    chunks.extend(file_chunks)
                    print(f"[DEBUG] Embedded code file: {rel_path} ({len(file_chunks)} chunks, type={ext})")
                
                else:
                    # Fallback for other files that might be text-like or common code files not in SUPPORTED_EXTENSIONS
                    # but we want to be conservative to avoid binary files
                    pass
        
        print(f"[DEBUG] Total repository ingestion: {len(chunks)} chunks from {repo_name}")
        return chunks

    def _process_readme(self, file_path: str, repo_url: str, rel_path: str) -> List[Chunk]:
        """Process README.md as markdown text."""
        text_ingester = TextIngester()
        raw_chunks = text_ingester.ingest(file_path)
        
        for chunk in raw_chunks:
            # Override metadata for GitHub context
            chunk.metadata.update({
                "repo_url": repo_url,
                "file_path": rel_path,
                "language": "markdown",
                "ingested_at": self._get_timestamp()
            })
            chunk.source_type = "github"
            chunk.source_name = repo_url
        
        return raw_chunks

    def _process_code_file(self, file_path: str, repo_url: str, rel_path: str) -> List[Chunk]:
        """Process a code file."""
        code_ingester = CodeIngester()
        raw_chunks = code_ingester.ingest(file_path)
        
        for chunk in raw_chunks:
            # Override metadata for GitHub context
            language = chunk.metadata.get("language", "unknown")
            chunk.metadata.update({
                "repo_url": repo_url,
                "file_path": rel_path,
                "language": language,
                "ingested_at": self._get_timestamp()
            })
            chunk.source_type = "github"
            chunk.source_name = repo_url
        
        return raw_chunks
