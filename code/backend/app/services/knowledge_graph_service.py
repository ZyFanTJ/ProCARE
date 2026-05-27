import json
from pathlib import Path
from typing import List, Dict, Any, Set
import logging
import re
from ..core.llm import LLMClient

# Try to import pypdf for PDF parsing
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

logger = logging.getLogger(__name__)

class KnowledgeGraphService:
    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.graph_file = storage_dir / "knowledge_graph.json"
        self._ensure_graph_exists()

    def _ensure_graph_exists(self):
        if not self.graph_file.exists():
            self.save_graph({"nodes": [], "links": []})

    def load_graph(self) -> Dict[str, Any]:
        try:
            if self.graph_file.exists():
                with open(self.graph_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {"nodes": [], "links": []}
        except Exception as e:
            logger.error(f"Error loading graph: {e}")
            return {"nodes": [], "links": []}

    def save_graph(self, graph_data: Dict[str, Any]):
        try:
            with open(self.graph_file, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving graph: {e}")

    def _extract_text_from_pdf(self, file_path: Path) -> str:
        """Extract text from the first few pages of a PDF."""
        if not HAS_PYPDF:
            logger.warning("pypdf not installed, skipping PDF text extraction")
            return ""
        try:
            reader = pypdf.PdfReader(file_path)
            text = ""
            # Limit to first 3 pages to save time and tokens
            for page in reader.pages[:3]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception as e:
            logger.error(f"Error reading PDF {file_path}: {e}")
            return ""

    def _extract_entities(self, text: str) -> List[str]:
        """Use LLM to extract key concepts and entities from text."""
        if not text or len(text.strip()) < 50:
            return []
        
        llm = LLMClient()
        prompt = f"""
        You are a medical research assistant. Extract key concepts, entities, and research topics (e.g., diseases, statistical methods, study types, drugs) from the following text.
        Focus on "RWS" (Real World Studies) related concepts if present.
        Return ONLY a JSON list of strings (max 8 items).
        Example: ["Diabetes", "Cohort Study", "Metformin", "Survival Analysis"]
        
        Text:
        {text[:2000]}
        """
        try:
            # Use a simple extraction pattern
            response = llm.generate(prompt=prompt)
            # Clean up response to find JSON list
            match = re.search(r'\[.*?\]', response, re.DOTALL)
            if match:
                json_str = match.group(0)
                entities = json.loads(json_str)
                return [str(e) for e in entities if isinstance(e, str)][:8]
            return []
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return []

    def refresh_graph_from_files(self):
        """
        Rebuild graph from files. 
        Preserves existing extracted entities for files that haven't changed (based on filename).
        """
        # Load existing graph to preserve cached entities
        existing_graph = self.load_graph()
        existing_nodes = {n["id"]: n for n in existing_graph.get("nodes", [])}
        
        files = [f for f in self.storage_dir.glob("*") if f.is_file() and f.name != "knowledge_graph.json"]
        
        final_file_nodes = []
        all_entities = set()
        file_to_entities = {} # file_id -> [entity_names]

        # 1. Process Files
        for f in files:
            file_id = f.name
            
            # Reuse existing node if available
            if file_id in existing_nodes:
                node = existing_nodes[file_id]
            else:
                node = {"id": file_id, "group": 1, "name": f.name, "val": 10}
            
            # Extract entities if PDF and not present
            if f.suffix.lower() == ".pdf" and "entities" not in node:
                logger.info(f"Extracting entities for {f.name}...")
                text = self._extract_text_from_pdf(f)
                if text:
                    entities = self._extract_entities(text)
                    if entities:
                        node["entities"] = entities
                        logger.info(f"Extracted: {entities}")
            
            # Also use filename keywords as fallback or addition
            filename_kws = [p for p in f.stem.replace("-", "_").split("_") if len(p) > 2 and not p.isdigit()]
            
            # Combine extracted entities and filename keywords
            extracted = node.get("entities", [])
            combined_entities = list(set(extracted + filename_kws))
            
            file_to_entities[file_id] = combined_entities
            for e in combined_entities:
                all_entities.add(e)
            
            final_file_nodes.append(node)

        # 2. Create Entity Nodes
        entity_nodes = []
        for entity in all_entities:
            entity_nodes.append({
                "id": f"entity_{entity}",
                "name": entity,
                "group": 2, # Concept/Entity
                "val": 5
            })

        # 3. Create Links
        links = []
        for file_node in final_file_nodes:
            file_id = file_node["id"]
            entities = file_to_entities.get(file_id, [])
            
            for entity in entities:
                links.append({
                    "source": file_id,
                    "target": f"entity_{entity}",
                    "value": 2
                })

        # Combine all nodes
        final_nodes = final_file_nodes + entity_nodes
        
        self.save_graph({"nodes": final_nodes, "links": links})
        return {"nodes": final_nodes, "links": links}

    def add_file_node(self, filename: str):
        # Trigger refresh for simplicity
        return self.refresh_graph_from_files()

    def remove_file_node(self, filename: str):
        # Trigger refresh for simplicity
        return self.refresh_graph_from_files()
