"""
Persona Database Utilities
==========================
SQLite-based persona management.
"""

import sqlite3
import os
from typing import List, Dict, Optional
from datetime import datetime


class PersonaDB:
    """SQLite wrapper for persona management"""
    
    DB_PATH = "artifacts/databases/personas.db"
    
    @classmethod
    def _ensure_db_dir(cls):
        """Create database directory"""
        os.makedirs(os.path.dirname(cls.DB_PATH), exist_ok=True)
    
    @classmethod
    def _get_connection(cls):
        """Get DB connection"""
        cls._ensure_db_dir()
        conn = sqlite3.connect(cls.DB_PATH)
        conn.row_factory = sqlite3.Row  # Dict-like access
        return conn
    
    @classmethod
    def init_db(cls):
        """Initialize database"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                personaId TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                sourceAudioId TEXT,
                createdAt TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
        print("Persona DB initialized")
    
    @classmethod
    def save_persona(cls, persona_data: Dict):
        """Save new persona"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO personas 
            (personaId, name, description, sourceAudioId, createdAt)
            VALUES (?, ?, ?, ?, ?)
        """, (
            persona_data.get("personaId"),
            persona_data.get("name"),
            persona_data.get("description", ""),
            persona_data.get("sourceAudioId", ""),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        print(f"Persona saved: {persona_data.get('name')}")
    
    @classmethod
    def list_personas(cls) -> List[Dict]:
        """List all personas"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM personas ORDER BY createdAt DESC")
        rows = cursor.fetchall()
        
        personas = [dict(row) for row in rows]
        
        conn.close()
        return personas
    
    @classmethod
    def get_persona(cls, persona_id: str) -> Optional[Dict]:
        """Get a specific persona"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM personas WHERE personaId = ?", (persona_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        return dict(row) if row else None
    
    @classmethod
    def get_persona_by_index(cls, index: int) -> Optional[Dict]:
        """Get persona by index (1-based)"""
        personas = cls.list_personas()
        if 0 < index <= len(personas):
            return personas[index - 1]
        return None
    
    @classmethod
    def delete_persona(cls, persona_id: str):
        """Delete persona"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM personas WHERE personaId = ?", (persona_id,))
        
        conn.commit()
        conn.close()
        print(f"Persona deleted: {persona_id}")
    
    @classmethod
    def count_personas(cls) -> int:
        """Total persona count"""
        conn = cls._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM personas")
        count = cursor.fetchone()[0]
        
        conn.close()
        return count


# Initialize DB on startup
PersonaDB.init_db()