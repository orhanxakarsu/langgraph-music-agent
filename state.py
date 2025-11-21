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
    

    generated_audio_url: List[str]
    task_id: List[str]
    music_retry_count: Optional[str]

