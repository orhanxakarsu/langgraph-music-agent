from typing import TypedDict, Optional, List, Dict, Literal, Annotated
from operator import add


class UnifiedState(TypedDict):
    """
    Unified state used by the entire system.
    UserCommunication, SystemSupervisor, MusicAgent, ImageAgent, VideoMerger
    all use this state.
    """
    
    # ============== USER & COMMUNICATION ==============
    phone_number: str
    messages: Annotated[List[str], add]  # String messages, combined with add
    user_request: Optional[str]  # User's original request
    
    # Communication agent decisions
    communication_action: Optional[str]
    communication_description: Optional[str]
    
    # ============== TASK MANAGEMENT ==============
    current_stage: Literal[
        "idle",                    # Initial
        "understanding",           # Understanding user request
        "planning",                # Planning tasks
        "generating_music",        # Generating music
        "awaiting_music_selection", # Waiting for music selection
        "generating_cover",        # Generating cover
        "generating_video",        # Generating video
        "awaiting_approval",       # Waiting for approval
        "delivering",              # Delivering
        "completed"                # Completed
    ]
    
    task_queue: List[str]          # Tasks to do: ["music", "cover", "video"]
    completed_tasks: List[str]     # Completed tasks
    
    # ============== MUSIC GENERATION ==============
    # Generation parameters
    music_prompt: Optional[str]
    music_style: Optional[str]
    music_title: Optional[str]
    music_instrumental: bool
    music_negative_tags: Optional[str]
    music_vocal_gender: Optional[str]
    music_style_weight: Optional[float]
    music_generation_model: str
    
    # Generated music (API generates 2)
    generated_audio_ids: List[str]
    generated_audio_urls: List[str]
    generated_audio_file_paths: List[str]
    
    # Selected music
    selected_audio_index: Optional[int]  # 0 or 1
    selected_audio_id: Optional[str]
    selected_audio_url: Optional[str]
    selected_audio_file_path: Optional[str]
    
    is_music_generated: bool
    is_music_selected: bool
    
    # ============== PERSONA ==============
    available_personas: List[Dict]
    selected_persona_id: Optional[str]
    
    # Persona saving
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
    retry_count: int  # How many times retried on error


def create_initial_state(phone_number: str, initial_message: str) -> UnifiedState:
    """Creates initial state for a new conversation"""
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
# Aliases for old states (for existing code to work)

MusicGenerationState = UnifiedState
ImageGenerationStateModel = UnifiedState
UserComminicationState = UnifiedState