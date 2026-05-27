from fastapi import APIRouter, HTTPException, Body
from pathlib import Path
import pandas as pd
import json
import shutil
import time
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = OUTPUT_DIR / "uploads"

# Ensure dirs exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class PreviewRequest(BaseModel):
    file_path: str

class Operation(BaseModel):
    type: str
    params: Dict[str, Any]

class ApplyRequest(BaseModel):
    file_path: str
    operations: List[Operation]
    save_as: Optional[str] = None

@router.get("/files")
async def list_files():
    files = []
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.glob("*"):
            if f.is_file() and f.suffix.lower() in ['.csv', '.xlsx', '.xls']:
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime
                })
    # Sort by mtime desc
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return {"files": files}

def load_df(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "File not found")
    
    try:
        if p.suffix.lower() == '.csv':
            return pd.read_csv(p)
        else:
            return pd.read_excel(p)
    except Exception as e:
        raise HTTPException(400, f"Failed to load file: {str(e)}")

@router.post("/preview")
async def preview_data(req: PreviewRequest):
    df = load_df(req.file_path)
    
    # Basic info
    info = {
        "rows": len(df),
        "cols": len(df.columns),
        "columns": []
    }
    
    for col in df.columns:
        info["columns"].append({
            "name": col,
            "type": str(df[col].dtype),
            "nulls": int(df[col].isnull().sum()),
            "unique": int(df[col].nunique())
        })
        
    # Head data (replace NaN with null for JSON)
    # limit to 100 rows for preview to be safe, but usually 10-20 is enough
    head = df.head(20).replace({float('nan'): None}).to_dict(orient='records')
    
    return {
        "info": info,
        "preview": head
    }

@router.post("/apply")
async def apply_ops(req: ApplyRequest):
    df = load_df(req.file_path)
    
    for op in req.operations:
        try:
            if op.type == 'fillna':
                col = op.params.get('column')
                val = op.params.get('value')
                # Try to convert value if column is numeric
                if col and col in df.columns:
                    if pd.api.types.is_numeric_dtype(df[col]):
                        try:
                            val = float(val)
                        except:
                            pass
                    df[col] = df[col].fillna(val)
                else:
                    df = df.fillna(val)
            elif op.type == 'dropna':
                subset = op.params.get('subset')
                if subset:
                    # ensure subset cols exist
                    valid_subset = [c for c in subset if c in df.columns]
                    if valid_subset:
                        df = df.dropna(subset=valid_subset)
                else:
                    df = df.dropna()
            elif op.type == 'rename':
                cols = op.params.get('columns')
                if cols:
                    df = df.rename(columns=cols)
            elif op.type == 'astype':
                col = op.params.get('column')
                dtype = op.params.get('dtype')
                if col and dtype and col in df.columns:
                    df[col] = df[col].astype(dtype)
            elif op.type == 'drop_col':
                cols = op.params.get('columns')
                if cols:
                    df = df.drop(columns=[c for c in cols if c in df.columns], errors='ignore')
        except Exception as e:
            raise HTTPException(400, f"Operation {op.type} failed: {str(e)}")
            
    # Save result
    if req.save_as:
        save_name = req.save_as
        if not save_name.endswith(('.csv', '.xlsx')):
            save_name += Path(req.file_path).suffix
        save_path = UPLOAD_DIR / save_name
    else:
        # Create copy with timestamp
        ts = int(time.time())
        stem = Path(req.file_path).stem
        # remove previous timestamp if looks like one
        # simplified: just append new ts
        suffix = Path(req.file_path).suffix
        save_path = UPLOAD_DIR / f"{stem}_cleaned_{ts}{suffix}"
        
    try:
        if save_path.suffix.lower() == '.csv':
            df.to_csv(save_path, index=False)
        else:
            df.to_excel(save_path, index=False)
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {str(e)}")
        
    return {
        "path": str(save_path),
        "filename": save_path.name
    }
