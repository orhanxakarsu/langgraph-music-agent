from typing import TypedDict, Optional, List, Dict, Literal,Annotated
from langgraph.graph import add_messages

class MusicGenerationState(TypedDict):
    request: Optional[str]
    request_details_from_supervisor: Annotated[str,add_messages]
    step_list: Annotated[str,add_messages]
    selected_topic: Optional[str]
    topic_description: Optional[str]
    music_style: Optional[str]
    music_title: Optional[str]
    
    generated_audio_urls: List[str]
    generated_audio_file_adress: List[str]
    generated_audio_ids: List[str]



    # Genel Olarak Seçilen Müzikler Buradan İlerleyecek.
    selected_audio_file_adress: Optional[str]
    selected_audio_id : Optional[str]
    selected_audio_url: Optional[str]

    selected_persona_id: Optional[str]
    music_generation_model: str = "V4"
    music_generation_duration_time: int = 180

    # Created Music Features
    task_id: Optional[str]
    prompt: Optional[str]
    style: Optional[str]
    instrumental: bool
    negative_tags: Optional[str]
    vocal_gender: Optional[str]
    style_weight: Optional[float]


    # persona saver information
    persona_saver_task_id: Optional[str]
    persona_saver_audio_id: Optional[str]
    persona_saver_name: Optional[str]
    persona_saver_description: Optional[str]
    is_persona_saved: Optional[bool]
    created_persona_id: Optional[str]


    # remake music






payload = {
                "prompt": params.prompt,
                "style": params.style,
                "title": params.title,
                "customMode": params.custom_mode,
                "personaId": state.get("persona_id"),
                "instrumental": params.instrumental,
                "model": "V4",
                "negativeTags": params.negative_tags,
                "vocalGender": params.vocal_gender,
                "styleWeight": params.style_weight,
                "weirdnessConstraint": params.weirdness_constraint,
                "audioWeight": params.audio_weight,
                "callBackUrl": "https://example.com/callback"
            }

