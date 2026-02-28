import os
import re
from typing import List
from backend.ingestion.base import BaseIngester, Chunk
from backend.config import CHUNKING

# Language extensions mapping
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".go": "go",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".rs": "rust",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".html": "html",
    ".css": "css",
    ".sh": "shell",
    ".bat": "batch",
    ".ps1": "powershell",
    ".sql": "sql"
}

SUPPORTED_EXTENSIONS = set(LANGUAGE_EXTENSIONS.keys())


class CodeIngester(BaseIngester):
    def __init__(self):
        self.chunk_size = CHUNKING["code"]["size"]
        self.overlap = CHUNKING["code"]["overlap"]

    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest code files by function/class boundaries."""
        chunks = []
        
        ext = os.path.splitext(source_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return chunks
        
        language = LANGUAGE_EXTENSIONS[ext]
        filename = os.path.basename(source_path)
        
        with open(source_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        # Try tree-sitter parsing first
        code_blocks = self._parse_with_tree_sitter(content, language)
        
        # Fallback to regex if tree-sitter fails or returns nothing
        if not code_blocks:
            code_blocks = self._parse_with_regex(content, language)
        
        for block in code_blocks:
            block_type = block.get("type", "unknown")
            name = block.get("name", "unknown")
            text = block.get("text", "")
            start_line = block.get("start_line", 0)
            end_line = block.get("end_line", 0)
            
            # Check if block exceeds chunk size
            if len(text) > self.chunk_size:
                # Split by inner blocks
                sub_chunks = self._split_large_block(block, language)
                for sub in sub_chunks:
                    chunk = Chunk(
                        text=sub["text"],
                        source_type="code",
                        source_name=filename,
                        metadata={
                            "file_path": source_path,
                            "language": language,
                            "function_name": sub.get("name") if sub.get("type") == "function" else None,
                            "class_name": sub.get("name") if sub.get("type") == "class" else None,
                            "start_line": sub.get("start_line", start_line),
                            "end_line": sub.get("end_line", end_line),
                            "ingested_at": self._get_timestamp()
                        }
                    )
                    chunks.append(chunk)
            else:
                chunk = Chunk(
                    text=text,
                    source_type="code",
                    source_name=filename,
                    metadata={
                        "file_path": source_path,
                        "language": language,
                        "function_name": name if block_type == "function" else None,
                        "class_name": name if block_type == "class" else None,
                        "start_line": start_line,
                        "end_line": end_line,
                        "ingested_at": self._get_timestamp()
                    }
                )
                chunks.append(chunk)
        
        return chunks

    def _parse_with_tree_sitter(self, content: str, language: str) -> List[dict]:
        """Parse code using tree-sitter for accurate function/class detection."""
        blocks = []
        
        try:
            import tree_sitter_python as tspython
            import tree_sitter_javascript as tsjavascript
            import tree_sitter_typescript as tstypescript
            import tree_sitter_java as tsjava
            import tree_sitter_go as tsgo
            import tree_sitter_ruby as tsruby
            import tree_sitter_rust as tsrust
            from tree_sitter import Language, Parser
            
            # Map language to tree-sitter language module
            lang_map = {
                "python": tspython,
                "javascript": tsjavascript,
                "typescript": tstypescript,
                "java": tsjava,
                "go": tsgo,
                "ruby": tsruby,
                "rust": tsrust
            }
            
            if language not in lang_map:
                return blocks
            
            lang_module = lang_map[language]
            parser = Parser(Language(lang_module.language()))
            
            tree = parser.parse(bytes(content, "utf8"))
            root = tree.root_node
            
            # Query for functions and classes
            query_map = {
                "python": """
                    (function_definition name: (identifier) @name) @function
                    (class_definition name: (identifier) @name) @class
                """,
                "javascript": """
                    (function_declaration name: (identifier) @name) @function
                    (class_declaration name: (identifier) @name) @class
                    (method_definition name: (property_identifier) @name) @function
                """,
                "typescript": """
                    (function_declaration name: (identifier) @name) @function
                    (class_declaration name: (type_identifier) @name) @class
                    (method_definition name: (property_identifier) @name) @function
                """,
                "java": """
                    (method_declaration name: (identifier) @name) @function
                    (class_declaration name: (identifier) @name) @class
                """,
                "go": """
                    (function_declaration name: (identifier) @name) @function
                    (type_declaration (type_spec name: (type_identifier) @name)) @class
                """,
                "ruby": """
                    (method name: (identifier) @name) @function
                    (class name: (constant) @name) @class
                """,
                "rust": """
                    (function_item name: (identifier) @name) @function
                    (struct_item name: (type_identifier) @name) @class
                """
            }
            
            if language not in query_map:
                return blocks
            
            query = parser.language.query(query_map[language])
            captures = query.captures(root)
            
            # Process captures
            seen_ranges = set()
            
            for node, capture_name in captures:
                if node.start_byte in seen_ranges:
                    continue
                
                seen_ranges.add(node.start_byte)
                
                block_type = "function" if "function" in capture_name else "class"
                
                # Get the name from captures
                name = "unknown"
                for n, cn in captures:
                    if cn == "name" and n.start_byte >= node.start_byte and n.end_byte <= node.end_byte:
                        name = content[n.start_byte:n.end_byte]
                        break
                
                text = content[node.start_byte:node.end_byte]
                
                blocks.append({
                    "type": block_type,
                    "name": name,
                    "text": text,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1
                })
            
        except ImportError:
            return blocks
        except Exception:
            return blocks
        
        return blocks

    def _parse_with_regex(self, content: str, language: str) -> List[dict]:
        """Fallback regex parsing for function/class detection."""
        blocks = []
        lines = content.split("\n")
        
        if language == "python":
            # Python: match def/class at start of line
            pattern = r'^(def |class )(\w+)'
            current_block = None
            current_indent = 0
            current_lines = []
            current_name = ""
            block_type = ""
            start_line = 0
            
            for i, line in enumerate(lines):
                match = re.match(pattern, line)
                if match:
                    # Save previous block
                    if current_block and current_lines:
                        blocks.append({
                            "type": block_type,
                            "name": current_name,
                            "text": "\n".join(current_lines),
                            "start_line": start_line,
                            "end_line": i
                        })
                    
                    block_type = "function" if match.group(1) == "def " else "class"
                    current_name = match.group(2)
                    current_indent = len(line) - len(line.lstrip())
                    current_lines = [line]
                    start_line = i + 1
                elif current_lines:
                    # Check if still in current block
                    if line.strip() == "" or (len(line) - len(line.lstrip()) > current_indent):
                        current_lines.append(line)
                    else:
                        # Block ended
                        blocks.append({
                            "type": block_type,
                            "name": current_name,
                            "text": "\n".join(current_lines),
                            "start_line": start_line,
                            "end_line": i
                        })
                        current_lines = []
                        current_name = ""
            
            # Save last block
            if current_lines:
                blocks.append({
                    "type": block_type,
                    "name": current_name,
                    "text": "\n".join(current_lines),
                    "start_line": start_line,
                    "end_line": len(lines)
                })
        
        elif language in ["javascript", "typescript"]:
            # JS/TS: match function/class declarations
            pattern = r'((?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:export\s+)?class\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))'
            
            for match in re.finditer(pattern, content):
                func_name = match.group(2) or match.group(3) or match.group(4)
                block_type = "class" if match.group(3) else "function"
                
                start_pos = match.start()
                start_line = content[:start_pos].count("\n") + 1
                
                # Find end of block (simplified)
                text = self._extract_js_block(content, match.start())
                end_line = start_line + text.count("\n")
                
                blocks.append({
                    "type": block_type,
                    "name": func_name,
                    "text": text,
                    "start_line": start_line,
                    "end_line": end_line
                })
        
        elif language == "java":
            # Java: match method/class declarations
            class_pattern = r'(?:public|private|protected)?\s*(?:abstract)?\s*class\s+(\w+)'
            method_pattern = r'(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*\{'
            
            for match in re.finditer(class_pattern, content):
                name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                text = self._extract_brace_block(content, match.start())
                end_line = start_line + text.count("\n")
                
                blocks.append({
                    "type": "class",
                    "name": name,
                    "text": text,
                    "start_line": start_line,
                    "end_line": end_line
                })
            
            for match in re.finditer(method_pattern, content):
                name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                text = self._extract_brace_block(content, match.start())
                end_line = start_line + text.count("\n")
                
                blocks.append({
                    "type": "function",
                    "name": name,
                    "text": text,
                    "start_line": start_line,
                    "end_line": end_line
                })
        
        elif language == "go":
            # Go: match func declarations
            pattern = r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*\)'
            
            for match in re.finditer(pattern, content):
                name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                text = self._extract_brace_block(content, match.start())
                end_line = start_line + text.count("\n")
                
                blocks.append({
                    "type": "function",
                    "name": name,
                    "text": text,
                    "start_line": start_line,
                    "end_line": end_line
                })
        
        else:
            # Generic: treat whole file as one chunk
            blocks.append({
                "type": "module",
                "name": os.path.basename(content[:50]),
                "text": content,
                "start_line": 1,
                "end_line": len(lines)
            })
        
        return blocks

    def _extract_brace_block(self, content: str, start_pos: int) -> str:
        """Extract a brace-delimited block starting from position."""
        brace_count = 0
        in_block = False
        end_pos = start_pos
        
        for i in range(start_pos, len(content)):
            char = content[i]
            
            if char == "{":
                brace_count += 1
                in_block = True
            elif char == "}":
                brace_count -= 1
                if in_block and brace_count == 0:
                    end_pos = i + 1
                    break
        
        return content[start_pos:end_pos]

    def _extract_js_block(self, content: str, start_pos: int) -> str:
        """Extract a JS function/class block."""
        return self._extract_brace_block(content, start_pos)

    def _split_large_block(self, block: dict, language: str) -> List[dict]:
        """Split a large code block by inner structures."""
        text = block["text"]
        sub_blocks = []
        
        # Try to find inner functions/blocks
        inner_blocks = self._parse_with_regex(text, language)
        
        if inner_blocks:
            for inner in inner_blocks:
                if len(inner["text"]) <= self.chunk_size:
                    sub_blocks.append({
                        "type": inner["type"],
                        "name": inner["name"],
                        "text": inner["text"],
                        "start_line": block["start_line"] + inner["start_line"] - 1,
                        "end_line": block["start_line"] + inner["end_line"] - 1
                    })
                else:
                    # Further split by lines
                    sub_blocks.extend(self._split_by_lines(inner, block["start_line"]))
        else:
            # Split by lines
            sub_blocks = self._split_by_lines(block, 0)
        
        return sub_blocks

    def _split_by_lines(self, block: dict, base_line: int) -> List[dict]:
        """Split a block by lines when no structure is found."""
        lines = block["text"].split("\n")
        sub_blocks = []
        current_lines = []
        current_start = block["start_line"]
        char_count = 0
        
        for i, line in enumerate(lines):
            if char_count + len(line) > self.chunk_size and current_lines:
                sub_blocks.append({
                    "type": block["type"],
                    "name": f"{block['name']}_part_{len(sub_blocks) + 1}",
                    "text": "\n".join(current_lines),
                    "start_line": current_start,
                    "end_line": current_start + len(current_lines) - 1
                })
                current_lines = []
                current_start = block["start_line"] + i
                char_count = 0
            
            current_lines.append(line)
            char_count += len(line) + 1
        
        if current_lines:
            sub_blocks.append({
                "type": block["type"],
                "name": f"{block['name']}_part_{len(sub_blocks) + 1}" if sub_blocks else block["name"],
                "text": "\n".join(current_lines),
                "start_line": current_start,
                "end_line": current_start + len(current_lines) - 1
            })
        
        return sub_blocks
