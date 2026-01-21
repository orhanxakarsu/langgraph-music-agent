from typing import TypedDict, Optional, List, Dict, Literal, Annotated
from operator import add


class UnifiedState(TypedDict):
    """
    Tüm sistemin kullandığı birleşik state.
    UserCommunication, SystemSupervisor, MusicAgent, ImageAgent, VideoMerger
    hepsi bu state'i kullanır.
    """
    
    # ============== USER & COMMUNICATION ==============
    phone_number: str
    messages: Annotated[List[str], add]  # String mesajlar, add ile birleştirilir
    user_request: Optional[str]  # Kullanıcının orijinal isteği
    
    # Communication agent kararları
    communication_action: Optional[str]
    communication_description: Optional[str]
    
    # ============== TASK MANAGEMENT ==============
    current_stage: Literal[
        "idle",                    # Başlangıç
        "understanding",           # Kullanıcı isteği anlaşılıyor
        "planning",                # Görevler planlanıyor
        "generating_music",        # Müzik üretiliyor
        "awaiting_music_selection", # Müzik seçimi bekleniyor
        "generating_cover",        # Kapak üretiliyor
        "generating_video",        # Video üretiliyor
        "awaiting_approval",       # Onay bekleniyor
        "delivering",              # Teslim ediliyor
        "completed"                # Tamamlandı
    ]
    
    task_queue: List[str]          # Yapılacak görevler: ["music", "cover", "video"]
    completed_tasks: List[str]     # Tamamlanan görevler
    
    # ============== MUSIC GENERATION ==============
    # Üretim parametreleri
    music_prompt: Optional[str]
    music_style: Optional[str]
    music_title: Optional[str]
    music_instrumental: bool
    music_negative_tags: Optional[str]
    music_vocal_gender: Optional[str]
    music_style_weight: Optional[float]
    music_generation_model: str
    
    # Üretilen müzikler (API 2 adet üretir)
    generated_audio_ids: List[str]
    generated_audio_urls: List[str]
    generated_audio_file_paths: List[str]
    
    # Seçilen müzik
    selected_audio_index: Optional[int]  # 0 veya 1
    selected_audio_id: Optional[str]
    selected_audio_url: Optional[str]
    selected_audio_file_path: Optional[str]
    
    is_music_generated: bool
    is_music_selected: bool
    
    # ============== PERSONA ==============
    available_personas: List[Dict]
    selected_persona_id: Optional[str]
    
    # Persona kaydetme
    persona_saver_task_id: Optional[str]
    persona_saver_audio_id: Optional[str]
    persona_saver_name: Optional[str]
    persona_saver_description: Optional[str]
    created_persona_id: Optional[str]
    is_persona_saved: bool
    
    # ============== IMAGE/COVER GENERATION ==============
    cover_description: Optional[str]
    cover_prompt: Optional[str]
    cover_image_path: Optional[str]
    cover_image_id: Optional[str]
    is_cover_generated: bool
    
    # ============== VIDEO GENERATION ==============
    video_file_path: Optional[str]
    is_video_generated: bool
    
    # ============== REMAKE ==============
    is_remake_requested: bool
    remake_instructions: Optional[str]
    
    # ============== ERROR HANDLING ==============
    error_message: Optional[str]
    last_error_stage: Optional[str]
    retry_count: int  # Hata durumunda kaç kez denendi


def create_initial_state(phone_number: str, initial_message: str) -> UnifiedState:
    """Yeni bir conversation için başlangıç state'i oluşturur"""
    return {
        # User & Communication
        "phone_number": phone_number,
        "messages": [f"User: {initial_message}"],
        "user_request": initial_message,
        "communication_action": None,
        "communication_description": None,
        
        # Task Management
        "current_stage": "idle",
        "task_queue": [],
        "completed_tasks": [],
        
        # Music Generation
        "music_prompt": None,
        "music_style": None,
        "music_title": None,
        "music_instrumental": False,
        "music_negative_tags": None,
        "music_vocal_gender": None,
        "music_style_weight": 0.65,
        "music_generation_model": "V4",
        
        "generated_audio_ids": [],
        "generated_audio_urls": [],
        "generated_audio_file_paths": [],
        
        "selected_audio_index": None,
        "selected_audio_id": None,
        "selected_audio_url": None,
        "selected_audio_file_path": None,
        
        "is_music_generated": False,
        "is_music_selected": False,
        
        # Persona
        "available_personas": [],
        "selected_persona_id": None,
        "persona_saver_task_id": None,
        "persona_saver_audio_id": None,
        "persona_saver_name": None,
        "persona_saver_description": None,
        "created_persona_id": None,
        "is_persona_saved": False,
        
        # Cover
        "cover_description": None,
        "cover_prompt": None,
        "cover_image_path": None,
        "cover_image_id": None,
        "is_cover_generated": False,
        
        # Video
        "video_file_path": None,
        "is_video_generated": False,
        
        # Remake
        "is_remake_requested": False,
        "remake_instructions": None,
        
        # Error
        "error_message": None,
        "last_error_stage": None,
        "retry_count": 0,
    }


# ============== BACKWARD COMPATIBILITY ==============
# Eski state'ler için alias'lar (mevcut kodların çalışması için)

MusicGenerationState = UnifiedState
ImageGenerationStateModel = UnifiedState
UserComminicationState = UnifiedState