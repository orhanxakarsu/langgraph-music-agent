from pydantic import BaseModel, Field
from typing import Optional, Literal, List


class PersonaChangerBaseModel(BaseModel):
    name: Optional[str] = Field(..., description="Name reflecting the persona's personality (Example: Electronic Pop Singer)")
    description: Optional[str] = Field(..., description="Personality description of the persona")


class MusicBaseModel(BaseModel):
    prompt: str = Field(..., description="Song lyrics or description")
    style: str = Field(..., description="Music style")
    title: str = Field(..., description="Song title")
    instrumental: bool = Field(..., description="Is it instrumental?")
    negative_tags: str = Field(default="", description="Unwanted characteristics")
    vocal_gender: Literal["f", "m"] = Field(..., description="Vocal gender")
    style_weight: float = Field(default=0.65, ge=0, le=1)
    weirdness_constraint: float = Field(default=0.65, ge=0, le=1)
    audio_weight: float = Field(default=0.65, ge=0, le=1)


class MusicGenerationAgentBaseModel(BaseModel):
    next: Literal["generate_music", "persona_saver", "remake_music", "return"] = Field(
        ..., description="Information about what the next step is."
    )
    reason: str = Field(..., description="Reason for making this decision")
    request_detail: str = Field(..., description="Detailed explanation of the incoming request for the next structure")


class CommunicationDecisionBaseModel(BaseModel):
    """Communication agent's decision model"""
    action: Literal[
        "send_message",
        "send_music",
        "send_cover",
        "send_video",
        "choice_persona",
        "task_planner",
        "wait_user",
        "finish"
    ] = Field(description="Action to take")
    
    description: str = Field(
        description="Detailed explanation of the action or message to send to user"
    )


class TaskPlannerDecisionBaseModel(BaseModel):
    """Task Planner's decision model - determines which tasks to perform"""
    
    tasks: List[Literal["music", "cover", "video", "persona_save", "remake"]] = Field(
        description="List of tasks to perform, ordered"
    )
    
    music_description: Optional[str] = Field(
        default=None,
        description="Detailed description for music generation (if music task exists)"
    )
    
    cover_description: Optional[str] = Field(
        default=None, 
        description="Description for cover generation (if cover task exists)"
    )
    
    remake_instructions: Optional[str] = Field(
        default=None,
        description="Instructions for remake (if remake task exists)"
    )
    
    response_to_user: str = Field(
        description="Response to give to user (processing started message)"
    )


class MusicSelectionBaseModel(BaseModel):
    """User's music selection"""
    
    selection: Literal["1", "2", "both", "neither", "remake"] = Field(
        description="User's selection: 1, 2, both, neither, or regenerate"
    )
    
    remake_feedback: Optional[str] = Field(
        default=None,
        description="If remake selected, user's feedback"
    )


class DeliveryDecisionBaseModel(BaseModel):
    """Delivery agent's decision model"""
    
    action: Literal[
        "deliver_music",
        "deliver_cover", 
        "deliver_video",
        "deliver_all",
        "ask_for_more",
        "finish"
    ] = Field(description="Delivery action")
    
    message: str = Field(description="Message to send to user")


class ImagePromptBaseModel(BaseModel):
    """Prompt model for image generator"""
    
    prompt: str = Field(description="Visual generation prompt (English)")
    style_notes: Optional[str] = Field(default=None, description="Style notes")