import re
import pandas as pd
from typing import List, Optional, Dict, Tuple, Any
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

def extract_code_block(text: str) -> str | None:
    """Extracts code block from LLM output."""
    if not text:
        return None
    # 优先提取 ```python ... ```
    m = re.search(r"```python\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 其次提取 ``` ... ```
    m = re.search(r"```\s*(.*?)```", text, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    return None

def safe_load_sheet(excel_path: str, sheet_name: str) -> pd.DataFrame:
    """
    Robustly loads a sheet from an Excel file.
    Handles common errors like file locking or missing sheets.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    
    try:
        # Load with pandas
        # Using openpyxl engine is standard for xlsx
        df = pd.read_excel(excel_path, sheet_name=sheet_name, engine='openpyxl')
        return df
    except ValueError as e:
        # Often happens if sheet_name doesn't exist
        # We can try to list sheets to give a better error
        try:
            xl = pd.ExcelFile(excel_path, engine='openpyxl')
            available = xl.sheet_names
            if sheet_name not in available:
                # Try case-insensitive match
                for s in available:
                    if s.lower() == sheet_name.lower():
                        print(f"[WARN] Sheet '{sheet_name}' not found, using '{s}' instead.")
                        return pd.read_excel(excel_path, sheet_name=s, engine='openpyxl')
            raise ValueError(f"Sheet '{sheet_name}' not found in {excel_path}. Available: {available}")
        except Exception:
            raise e
    except Exception as e:
        raise RuntimeError(f"Failed to load sheet '{sheet_name}': {e}")

def resolve_columns(df: pd.DataFrame, expected_concepts: List[str]) -> Dict[str, str]:
    """
    Resolves expected concepts to actual column names in the DataFrame.
    Returns a mapping: {concept: actual_column_name}
    """
    actual_cols = df.columns.tolist()
    mapping = {}
    
    # Normalize actual columns for matching (lowercase, strip)
    norm_actual = {str(c).lower().strip(): c for c in actual_cols}
    
    for concept in expected_concepts:
        # 1. Exact match
        if concept in actual_cols:
            mapping[concept] = concept
            continue
            
        # 2. Case-insensitive match
        norm_concept = str(concept).lower().strip()
        if norm_concept in norm_actual:
            mapping[concept] = norm_actual[norm_concept]
            continue
            
        # 3. Fuzzy match (simple containment)
        # This is risky but useful for slight variations
        found = False
        for norm_col, original_col in norm_actual.items():
            if norm_concept in norm_col or norm_col in norm_concept:
                mapping[concept] = original_col
                found = True
                break
        
        if not found:
            print(f"[WARN] Could not resolve column for concept '{concept}'.")
            
    return mapping

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Performs standard cleaning:
    - Drops empty columns/rows
    - Infers objects to numbers where possible
    """
    df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
    # Attempt to convert object columns to numeric if they contain numbers
    for col in df.select_dtypes(include=['object']):
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df

# --- Journal-Grade Plotting Helpers ---

def set_publication_style():
    """
    Sets Matplotlib/Seaborn style to academic journal standards.
    Features: Arial font, clean spines, high DPI ready.
    """
    # Use seaborn for better defaults
    sns.set_theme(style="ticks", context="paper")
    
    # Configure rcParams for publication quality
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 10,
        'axes.labelsize': 11,
        'axes.titlesize': 12,
        'axes.titleweight': 'bold',
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        'legend.title_fontsize': 10,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'lines.linewidth': 1.5,
        'patch.linewidth': 1.0,
    })

def get_palette(n_colors: int = 10, palette_name: str = "nejm", n: Optional[int] = None) -> List[str]:
    """
    Returns a list of hex codes for journal-style palettes.
    Supports: nejm, nature, lancet, set2, paired.
    Compatible with 'n' argument for legacy calls.
    """
    if n is not None:
        n_colors = n
    
    # Custom palettes inspired by journals
    palettes = {
        "nejm": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD", "#FFDC91", "#EE4C97"],
        "nature": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4", "#91D1C2", "#DC0000"],
        "lancet": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91", "#AD002A", "#ADB6B6"],
    }
    
    if palette_name in palettes:
        colors = palettes[palette_name]
    else:
        # Fallback to seaborn
        try:
            return sns.color_palette(palette_name, n_colors).as_hex()
        except ValueError:
            return sns.color_palette("deep", n_colors).as_hex()
            
    if n_colors > len(colors):
        # Cycle if not enough
        return (colors * (n_colors // len(colors) + 1))[:n_colors]
    return colors[:n_colors]

def save_plot(fig: plt.Figure, path: str, close: bool = True):
    """
    Saves a figure with high DPI and tight layout.
    Also saves a PDF version for vector graphics.
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Save PNG (Raster)
        fig.savefig(path, dpi=300, bbox_inches='tight', pad_inches=0.1)
        print(f"[INFO] Saved plot: {path}")
        
        # Save PDF (Vector) - optional but recommended for papers
        # Replace extension
        base, _ = os.path.splitext(path)
        pdf_path = f"{base}.pdf"
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
    except Exception as e:
        print(f"[ERROR] Failed to save plot {path}: {e}")
    finally:
        if close:
            plt.close(fig)

def add_stat_annotation(ax, x1: float, x2: float, y: float, h: float, p_value: float, text: str = None):
    """
    Adds a statistical bracket with P-value to the axes.
    (x1, x2): x-coordinates of the bars being compared.
    y: y-coordinate of the bracket line.
    h: height of the bracket legs.
    """
    if text is None:
        if p_value < 0.001:
            text = "***"
        elif p_value < 0.01:
            text = "**"
        elif p_value < 0.05:
            text = "*"
        else:
            text = "ns"
            
    ax.plot([x1, x1, x2, x2], [y, y+h, y+h, y], lw=1.0, c='k')
    ax.text((x1+x2)*.5, y+h, text, ha='center', va='bottom', color='k')
