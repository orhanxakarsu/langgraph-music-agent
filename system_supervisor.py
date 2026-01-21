"""
System Supervisor Agent
=======================
The brain of the entire system. Handles user communication, task planning,
and coordinates all sub-agents.

Flow:
1. communication_agent: Understands user message
2. task_planner: Plans tasks
3. music_generator: Generates music
4. music_selection_handler: Music selection
5. cover_generator: Generates cover
6. video_generator: Generates video
7. delivery_agent: Delivers results
"""

import os
import time
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from dotenv import load_dotenv

from state import UnifiedState, create_initial_state
from base_models import (
    CommunicationDecisionBaseModel,
    TaskPlannerDecisionBaseModel,
    MusicBaseModel,
    MusicSelectionBaseModel,
    ImagePromptBaseModel,
    DeliveryDecisionBaseModel
)
from whatsapp_helper import WhatsApp
from personadb_utils import PersonaDB
from suno_ai import SunoAPI
from cover_generator import ImageGeneratorAgent, GoogleApi

load_dotenv()


def messages_to_string(messages: list, last_n: int = 10) -> str:
    """
    Converts message list to string.
    Can be HumanMessage, AIMessage or string.
    """
    result = []
    for msg in messages[-last_n:]:
        if isinstance(msg, str):
            result.append(msg)
        elif hasattr(msg, 'content'):
            role = msg.__class__.__name__.replace("Message", "")
            result.append(f"{role}: {msg.content}")
        else:
            result.append(str(msg))
    return "\n".join(result)


class SystemSupervisor:
    """
    Main supervisor that manages the entire system.
    Coordinates all agents within a single workflow.
    """

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o")
        self.message_helper = WhatsApp()
        self.persona_db = PersonaDB()
        self.suno_api = SunoAPI()
        self.google_api = GoogleApi()
        self.memory = MemorySaver()
        self.workflow = None

    # ================================================================
    # COMMUNICATION LAYER
    # ================================================================

    def communication_agent(self, state: UnifiedState):
        """
        Main communication agent - analyzes user message and determines action.
        """
        
        system_message = """You are the intelligent assistant of a music production company.
You communicate with users via WhatsApp.

# TASKS:
1. Understand what the user wants
2. Select appropriate action
3. Maintain natural and friendly communication

# ACTIONS:
- **task_planner**: There's a new production task (generate music/cover/video)
- **send_message**: Send info message, then wait for response
- **send_music**: Send ready music
- **send_cover**: Send ready cover image
- **send_video**: Send ready video
- **choice_persona**: Show persona list
- **wait_user**: Wait for user response
- **finish**: End conversation

# CURRENT STATUS:
- Stage: {current_stage}
- Music generated: {is_music_generated}
- Music selected: {is_music_selected}
- Cover generated: {is_cover_generated}
- Video generated: {is_video_generated}
- Task queue: {task_queue}
- Completed tasks: {completed_tasks}

# DECISION LOGIC:
1. User wants something new → task_planner
2. Music ready but not sent → send_music
3. Cover ready but not sent → send_cover
4. Video ready but not sent → send_video
5. Asked a question → wait_user
6. Everything done and user satisfied → finish

# IMPORTANT:
- After sending message go to wait_user
- If you need info from user, ask first
- Be friendly and helpful
- If ERROR and retry count reached 2, DON'T go to task_planner, apologize to user and go to wait_user
- Don't keep going to task_planner for the same task (creates error loop)
"""
        
        human_message = """
# Recent Messages:
{messages}

# Error Status:
{error_info}

Analyze the situation and determine action.
"""

        template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        chain = template | self.llm.with_structured_output(CommunicationDecisionBaseModel)

        error_info = "None"
        if state.get("error_message"):
            retry = state.get("retry_count", 0)
            error_info = f"Error: {state['error_message']} (Attempt: {retry}/2)"

        result = chain.invoke({
            "messages": messages_to_string(state.get("messages", [])),
            "current_stage": state.get("current_stage", "idle"),
            "is_music_generated": state.get("is_music_generated", False),
            "is_music_selected": state.get("is_music_selected", False),
            "is_cover_generated": state.get("is_cover_generated", False),
            "is_video_generated": state.get("is_video_generated", False),
            "task_queue": state.get("task_queue", []),
            "completed_tasks": state.get("completed_tasks", []),
            "error_info": error_info
        })

        print(f"\n{'='*50}")
        print(f"COMMUNICATION AGENT")
        print(f"   Action: {result.action}")
        print(f"   Description: {result.description[:100]}...")
        print(f"{'='*50}\n")

        return Command(
            update={
                "communication_action": result.action,
                "communication_description": result.description
            },
            goto=result.action
        )

    def send_message(self, state: UnifiedState):
        """Sends message to user"""
        
        message = state.get("communication_description", "")
        phone = state["phone_number"]
        
        try:
            self.message_helper.send_message(phone, message)
            print(f"Message sent: {phone}")
            
            return Command(
                update={
                    "messages": [f"Assistant: {message}"]
                },
                goto="wait_user"
            )
        except Exception as e:
            print(f"Message error: {e}")
            return Command(
                update={
                    "messages": [f"System: Message could not be sent - {e}"],
                    "error_message": str(e)
                },
                goto="communication_agent"
            )

    def wait_user(self, state: UnifiedState):
        """Human-in-the-loop: Waits for user response"""
        
        print("\nWaiting for user response...")
        
        user_response = interrupt("Waiting for user response...")
        
        print(f"User response received: {user_response}")
        
        return Command(
            update={
                "messages": [f"User: {user_response}"],
                "user_request": user_response
            },
            goto="communication_agent"
        )

    def choice_persona(self, state: UnifiedState):
        """Persona selection"""
        
        phone = state["phone_number"]
        personas = self.persona_db.list_personas()
        
        if not personas:
            message = "No personas saved yet. First, generate music and save a style you like!"
            self.message_helper.send_message(phone, message)
            
            return Command(
                update={"messages": [f"Assistant: {message}"]},
                goto="wait_user"
            )
        
        # Format persona list
        message = "Saved Personas:\n\n"
        for idx, persona in enumerate(personas, 1):
            message += f"{idx}. {persona['name']}\n"
            message += f"   {persona.get('description', 'No description')}\n\n"
        message += "\nWhich persona would you like to use? (Send number)"
        
        self.message_helper.send_message(phone, message)
        
        return Command(
            update={
                "messages": [f"Assistant: {message}"],
                "available_personas": personas
            },
            goto="wait_user"
        )

    # ================================================================
    # TASK PLANNING LAYER
    # ================================================================

    def task_planner(self, state: UnifiedState):
        """
        Task planner - analyzes user request and determines tasks to perform.
        """
        
        system_message = """You are a music production planner.
Analyze user request and determine which tasks to perform.

# TASKS:
- **music**: Generate new music
- **cover**: Generate album/song cover
- **video**: Create music video (music + cover combination)
- **persona_save**: Save current music's style
- **remake**: Regenerate/edit current music

# RULES:
1. Video requires both music AND cover first
2. Remake requires music to be generated first
3. Saving persona requires a selected music
4. Order tasks logically: music → cover → video

# CURRENT STATUS:
- Has music: {has_music}
- Has selected music: {has_selected_music}
- Has cover: {has_cover}

Plan tasks according to user request.
"""

        human_message = """
User request: {user_request}

Recent messages:
{recent_messages}

Plan tasks and prepare an informative message for user.
"""

        template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        chain = template | self.llm.with_structured_output(TaskPlannerDecisionBaseModel)

        result = chain.invoke({
            "user_request": state.get("user_request", ""),
            "recent_messages": messages_to_string(state.get("messages", []), last_n=5),
            "has_music": state.get("is_music_generated", False),
            "has_selected_music": state.get("is_music_selected", False),
            "has_cover": state.get("is_cover_generated", False)
        })

        print(f"\n{'='*50}")
        print(f"TASK PLANNER")
        print(f"   Tasks: {result.tasks}")
        print(f"   Music desc: {result.music_description}")
        print(f"   Cover desc: {result.cover_description}")
        print(f"{'='*50}\n")

        # Inform user
        phone = state["phone_number"]
        self.message_helper.send_message(phone, result.response_to_user)

        # Determine first task
        next_node = "communication_agent"
        if result.tasks:
            first_task = result.tasks[0]
            if first_task == "music":
                next_node = "music_generator"
            elif first_task == "cover":
                next_node = "cover_generator"
            elif first_task == "video":
                next_node = "video_generator"
            elif first_task == "remake":
                next_node = "music_remake"

        return Command(
            update={
                "current_stage": "planning",
                "task_queue": result.tasks,
                "music_prompt": result.music_description,
                "cover_description": result.cover_description,
                "remake_instructions": result.remake_instructions,
                "messages": [f"Assistant: {result.response_to_user}"]
            },
            goto=next_node
        )

    # ================================================================
    # MUSIC GENERATION LAYER
    # ================================================================

    def music_generator(self, state: UnifiedState):
        """Generates music - Uses Suno API"""
        
        print("\nMUSIC GENERATOR started...")
        
        # Retry control - max 2 attempts
        retry_count = state.get("retry_count", 0)
        if retry_count >= 2:
            print(f"   Max retry count reached ({retry_count})")
            
            # Send error message to user
            phone = state["phone_number"]
            self.message_helper.send_message(
                phone,
                "Having trouble with music generation. Please try again later or make a different request."
            )
            
            return Command(
                update={
                    "error_message": "Max retry exceeded",
                    "current_stage": "idle",
                    "retry_count": 0,
                    "task_queue": [],
                    "messages": ["System: Music generation failed - max retry"]
                },
                goto="wait_user"
            )
        
        system_message = """You are a professional music creation expert.

# RULES:
- custom_mode: True (for advanced settings)
- instrumental: True for instrumental, False for vocals
- prompt: Lyrics (max 3000 chars) - Write lyrics if with vocals
- style: Music style (max 200 chars)
- title: Title (max 80 chars)
- All instructions in ENGLISH, only lyrics in requested language

# IMPORTANT:
- Pay attention to rhymes when writing lyrics
- Be minimalist but impactful
- Specify unwanted elements with negative_tags
"""

        human_message = """
Music request: {music_description}

Create detailed music parameters for this request.
"""

        template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        chain = template | self.llm.with_structured_output(MusicBaseModel)

        music_params = chain.invoke({
            "music_description": state.get("music_prompt", state.get("user_request", ""))
        })

        print(f"   Style: {music_params.style}")
        print(f"   Title: {music_params.title}")
        print(f"   Instrumental: {music_params.instrumental}")

        # Call Suno API
        api_result = self.suno_api.create_music(state, music_params)

        if api_result["is_generated"]:
            updated_state = api_result["current_state"]
            
            # Filter None values
            audio_paths = [p for p in updated_state.get("generated_audio_file_adress", []) if p]
            audio_ids = updated_state.get("generated_audio_ids", [])
            audio_urls = updated_state.get("generated_audio_urls", [])
            
            print(f"   Music generated!")
            print(f"   Audio IDs: {audio_ids}")
            print(f"   Downloaded paths: {audio_paths}")
            
            # If no music downloaded, error
            if not audio_paths:
                print("   Music could not be downloaded!")
                return Command(
                    update={
                        "error_message": "Music could not be downloaded",
                        "last_error_stage": "music_generator",
                        "retry_count": retry_count + 1,
                        "messages": [f"System: Music download failed (attempt {retry_count + 1})"]
                    },
                    goto="communication_agent"
                )
            
            # Update task queue
            remaining_tasks = state.get("task_queue", [])[1:]
            completed = state.get("completed_tasks", []) + ["music"]
            
            return Command(
                update={
                    "current_stage": "awaiting_music_selection",
                    "is_music_generated": True,
                    "generated_audio_ids": audio_ids,
                    "generated_audio_urls": audio_urls,
                    "generated_audio_file_paths": audio_paths,
                    "music_style": music_params.style,
                    "music_title": music_params.title,
                    "task_queue": remaining_tasks,
                    "completed_tasks": completed,
                    "retry_count": 0,
                    "messages": [f"System: {len(audio_paths)} music tracks generated, awaiting selection"]
                },
                goto="music_selection_prompt"
            )
        else:
            print(f"   Music could not be generated!")
            return Command(
                update={
                    "error_message": api_result.get("error", "Music could not be generated"),
                    "last_error_stage": "music_generator",
                    "retry_count": retry_count + 1,
                    "messages": [f"System: Music generation error (attempt {retry_count + 1})"]
                },
                goto="communication_agent"
            )

    def music_selection_prompt(self, state: UnifiedState):
        """Sends 2 music tracks as links to user and asks for selection"""
        
        phone = state["phone_number"]
        audio_paths = state.get("generated_audio_file_paths", [])
        
        # Filter None values
        audio_paths = [p for p in audio_paths if p]
        
        print(f"\nMUSIC SELECTION - Sending {len(audio_paths)} music links...")
        
        if not audio_paths:
            print("   No downloaded music!")
            self.message_helper.send_message(
                phone,
                "Music could not be downloaded. Should we try again?"
            )
            return Command(
                update={
                    "messages": ["System: Music files not found"],
                    "current_stage": "idle"
                },
                goto="wait_user"
            )
        
        # Description message
        message = "I've created 2 different versions for you!\n\n"
        message += "Your options:\n"
        message += "- '1' or '2' - Select one\n"
        message += "- 'both' - Use both\n"
        message += "- 'neither' - Regenerate\n"
        message += "- Write feedback - Tell me what to change"
        
        self.message_helper.send_message(phone, message)
        time.sleep(1)
        
        # Send music links as SEPARATE messages (for clickability)
        for idx, audio_path in enumerate(audio_paths[:2], 1):
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(audio_path)
                else:
                    filename = os.path.basename(audio_path)
                    file_url = f"http://localhost:5000/files/music/{filename}"
                
                link_message = f"Version {idx}:\n{file_url}"
                self.message_helper.send_message(phone, link_message)
                time.sleep(2)
                
                print(f"   Music {idx} link sent: {file_url}")
            except Exception as e:
                print(f"   Music {idx} link could not be sent: {e}")
        
        return Command(
            update={
                "messages": [f"Assistant: {message}", "System: Music links sent"],
                "current_stage": "awaiting_music_selection"
            },
            goto="music_selection_handler"
        )

    def music_selection_handler(self, state: UnifiedState):
        """Waits for and processes user's music selection"""
        
        print("\nWaiting for music selection...")
        
        user_response = interrupt("Waiting for music selection...")
        
        print(f"User response: {user_response}")
        
        # Analyze response
        response_lower = user_response.lower().strip()
        
        audio_ids = state.get("generated_audio_ids", [])
        audio_urls = state.get("generated_audio_urls", [])
        audio_paths = state.get("generated_audio_file_paths", [])
        
        selected_index = None
        next_node = "communication_agent"
        updates = {"messages": [f"User: {user_response}"]}
        
        if response_lower in ["1", "one", "first"]:
            selected_index = 0
            updates["messages"].append("System: First music selected")
            
        elif response_lower in ["2", "two", "second"]:
            selected_index = 1
            updates["messages"].append("System: Second music selected")
            
        elif "both" in response_lower:
            selected_index = 0
            updates["messages"].append("System: Both tracks accepted, using first one")
            
        elif "neither" in response_lower or "regenerate" in response_lower or "again" in response_lower:
            updates["is_remake_requested"] = True
            updates["remake_instructions"] = user_response
            updates["current_stage"] = "generating_music"
            updates["messages"].append("System: Music will be regenerated")
            next_node = "music_generator"
            
        else:
            # Treat as feedback - do remake
            updates["is_remake_requested"] = True
            updates["remake_instructions"] = user_response
            updates["current_stage"] = "generating_music"
            updates["messages"].append(f"System: Will regenerate based on feedback: {user_response}")
            next_node = "music_generator"
        
        # If selection made, update state
        if selected_index is not None:
            updates["selected_audio_index"] = selected_index
            updates["selected_audio_id"] = audio_ids[selected_index] if audio_ids else None
            updates["selected_audio_url"] = audio_urls[selected_index] if audio_urls else None
            updates["selected_audio_file_path"] = audio_paths[selected_index] if audio_paths else None
            updates["is_music_selected"] = True
            updates["current_stage"] = "generating_cover" if "cover" in state.get("task_queue", []) else "delivering"
            
            # Move to next task
            if "cover" in state.get("task_queue", []):
                next_node = "cover_generator"
            else:
                next_node = "delivery_agent"
        
        return Command(update=updates, goto=next_node)

    def music_remake(self, state: UnifiedState):
        """Regenerates existing music"""
        
        print("\nMUSIC REMAKE started...")
        
        system_message = """Edit existing music based on user feedback.
Keep original style but apply requested changes."""

        human_message = """
Original style: {original_style}
Original title: {original_title}
User feedback: {feedback}

Create new music parameters.
"""

        template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        chain = template | self.llm.with_structured_output(MusicBaseModel)

        remake_params = chain.invoke({
            "original_style": state.get("music_style", ""),
            "original_title": state.get("music_title", ""),
            "feedback": state.get("remake_instructions", "")
        })

        # Remake with Suno API
        api_result = self.suno_api.remake_music(state, remake_params)

        if api_result["is_generated"]:
            updated_state = api_result["current_state"]
            
            return Command(
                update={
                    "is_music_generated": True,
                    "is_music_selected": False,
                    "generated_audio_ids": updated_state.get("generated_audio_ids", []),
                    "generated_audio_urls": updated_state.get("generated_audio_urls", []),
                    "generated_audio_file_paths": updated_state.get("generated_audio_file_adress", []),
                    "is_remake_requested": False,
                    "messages": ["System: Music regenerated"]
                },
                goto="music_selection_prompt"
            )
        else:
            return Command(
                update={
                    "error_message": "Remake failed",
                    "messages": ["System: Music could not be regenerated"]
                },
                goto="communication_agent"
            )

    # ================================================================
    # COVER GENERATION LAYER  
    # ================================================================

    def cover_generator(self, state: UnifiedState):
        """Generates album cover"""
        
        print("\nCOVER GENERATOR started...")
        
        system_message = """You are a music cover art creation expert.
        
# RULES:
- Minimalist and impactful designs
- Visuals that reflect the music's soul
- Avoid excessive detail and complexity
- Prompt should be in ENGLISH
- Don't add text to cover (unless requested)
"""

        human_message = """
Music style: {music_style}
Music title: {music_title}
Additional description: {cover_description}

Create an impactful cover design prompt for this music.
"""

        template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        chain = template | self.llm.with_structured_output(ImagePromptBaseModel)

        result = chain.invoke({
            "music_style": state.get("music_style", ""),
            "music_title": state.get("music_title", ""),
            "cover_description": state.get("cover_description", "")
        })

        print(f"   Prompt: {result.prompt[:100]}...")

        # Generate image with Google API
        import uuid
        cover_id = str(uuid.uuid4())
        image_path = f"artifacts/generated_images/{cover_id}.png"
        
        try:
            generated_path = self.google_api.generate_image(result.prompt, image_path)
            
            # Update task queue
            remaining_tasks = [t for t in state.get("task_queue", []) if t != "cover"]
            completed = state.get("completed_tasks", []) + ["cover"]
            
            print(f"   Cover generated: {generated_path}")
            
            # Is there a video task?
            next_node = "video_generator" if "video" in remaining_tasks else "delivery_agent"
            
            return Command(
                update={
                    "cover_image_path": generated_path,
                    "cover_image_id": cover_id,
                    "cover_prompt": result.prompt,
                    "is_cover_generated": True,
                    "current_stage": "generating_video" if "video" in remaining_tasks else "delivering",
                    "task_queue": remaining_tasks,
                    "completed_tasks": completed,
                    "messages": ["System: Cover generated"]
                },
                goto=next_node
            )
        except Exception as e:
            print(f"   Cover could not be generated: {e}")
            return Command(
                update={
                    "error_message": str(e),
                    "last_error_stage": "cover_generator",
                    "messages": [f"System: Cover generation error: {e}"]
                },
                goto="communication_agent"
            )

    # ================================================================
    # VIDEO GENERATION LAYER
    # ================================================================

    def video_generator(self, state: UnifiedState):
        """Music + Cover = Video"""
        
        print("\nVIDEO GENERATOR started...")
        
        import subprocess
        import uuid
        
        image_path = state.get("cover_image_path")
        audio_path = state.get("selected_audio_file_path")
        
        print(f"   Image: {image_path}")
        print(f"   Audio: {audio_path}")
        
        if not image_path or not audio_path:
            return Command(
                update={
                    "error_message": "Missing file for video",
                    "messages": ["System: Music or cover missing for video"]
                },
                goto="communication_agent"
            )
        
        try:
            os.makedirs("artifacts/final_videos", exist_ok=True)
            output_name = f"{uuid.uuid4()}.mp4"
            output_path = f"artifacts/final_videos/{output_name}"
            
            # FFmpeg command
            command = [
                'ffmpeg',
                '-loop', '1',
                '-i', image_path,
                '-i', audio_path,
                '-c:v', 'libx264',
                '-tune', 'stillimage',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-pix_fmt', 'yuv420p',
                '-shortest',
                '-y',
                output_path
            ]
            
            print("   Running FFmpeg...")
            subprocess.run(command, check=True, capture_output=True, text=True)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                # Update task queue
                remaining_tasks = [t for t in state.get("task_queue", []) if t != "video"]
                completed = state.get("completed_tasks", []) + ["video"]
                
                print(f"   Video created: {output_path}")
                
                return Command(
                    update={
                        "video_file_path": output_path,
                        "is_video_generated": True,
                        "current_stage": "delivering",
                        "task_queue": remaining_tasks,
                        "completed_tasks": completed,
                        "messages": ["System: Video created"]
                    },
                    goto="delivery_agent"
                )
            else:
                raise Exception("Video file could not be created")
                
        except Exception as e:
            print(f"   Video error: {e}")
            return Command(
                update={
                    "error_message": str(e),
                    "last_error_stage": "video_generator",
                    "messages": [f"System: Video could not be created: {e}"]
                },
                goto="communication_agent"
            )

    # ================================================================
    # DELIVERY LAYER
    # ================================================================

    def delivery_agent(self, state: UnifiedState):
        """Delivers generated content to user as links"""
        
        print("\nDELIVERY AGENT started...")
        
        phone = state["phone_number"]
        delivered = []
        
        # Music delivery (as link)
        if state.get("is_music_selected") and state.get("selected_audio_file_path"):
            audio_path = state["selected_audio_file_path"]
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(audio_path)
                else:
                    filename = os.path.basename(audio_path)
                    file_url = f"http://localhost:5000/files/music/{filename}"
                
                self.message_helper.send_message(phone, f"Your selected music:\n{file_url}")
                delivered.append("music")
                print(f"   Music link delivered: {file_url}")
                time.sleep(2)
            except Exception as e:
                print(f"   Music delivery error: {e}")
        
        # Cover delivery (as link)
        if state.get("is_cover_generated") and state.get("cover_image_path"):
            cover_path = state["cover_image_path"]
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(cover_path)
                else:
                    filename = os.path.basename(cover_path)
                    file_url = f"http://localhost:5000/files/image/{filename}"
                
                self.message_helper.send_message(phone, f"Album cover:\n{file_url}")
                delivered.append("cover")
                print(f"   Cover link delivered: {file_url}")
                time.sleep(2)
            except Exception as e:
                print(f"   Cover delivery error: {e}")
        
        # Video delivery (as link)
        if state.get("is_video_generated") and state.get("video_file_path"):
            video_path = state["video_file_path"]
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(video_path)
                else:
                    filename = os.path.basename(video_path)
                    file_url = f"http://localhost:5000/files/video/{filename}"
                
                self.message_helper.send_message(phone, f"Your music video:\n{file_url}")
                delivered.append("video")
                print(f"   Video link delivered: {file_url}")
                time.sleep(2)
            except Exception as e:
                print(f"   Video delivery error: {e}")
        
        # Closing message
        if delivered:
            closing_message = "All content is ready! Would you like anything else?"
        else:
            closing_message = "Hmm, couldn't find content to send. What would you like me to do?"
        
        self.message_helper.send_message(phone, closing_message)
        
        return Command(
            update={
                "current_stage": "completed",
                "messages": [
                    f"System: Delivered: {delivered}",
                    f"Assistant: {closing_message}"
                ]
            },
            goto="wait_user"
        )

    def finish(self, state: UnifiedState):
        """Terminates workflow"""
        print("\nWORKFLOW COMPLETED")
        return state

    # ================================================================
    # MEDIA SENDERS (Direct)
    # ================================================================

    def send_music(self, state: UnifiedState):
        """Sends selected music"""
        phone = state["phone_number"]
        audio_path = state.get("selected_audio_file_path")
        
        if not audio_path:
            return Command(
                update={"messages": ["System: No music to send"]},
                goto="communication_agent"
            )
        
        try:
            self.message_helper.send_audio(phone, audio_path)
            return Command(
                update={"messages": ["System: Music sent"]},
                goto="communication_agent"
            )
        except Exception as e:
            return Command(
                update={"messages": [f"System: Music could not be sent: {e}"]},
                goto="communication_agent"
            )

    def send_cover(self, state: UnifiedState):
        """Sends cover image"""
        phone = state["phone_number"]
        cover_path = state.get("cover_image_path")
        
        if not cover_path:
            return Command(
                update={"messages": ["System: No cover to send"]},
                goto="communication_agent"
            )
        
        try:
            self.message_helper.send_message(phone, "Cover image:")
            return Command(
                update={"messages": ["System: Cover sent"]},
                goto="communication_agent"
            )
        except Exception as e:
            return Command(
                update={"messages": [f"System: Cover could not be sent: {e}"]},
                goto="communication_agent"
            )

    def send_video(self, state: UnifiedState):
        """Sends video"""
        phone = state["phone_number"]
        video_path = state.get("video_file_path")
        
        if not video_path:
            return Command(
                update={"messages": ["System: No video to send"]},
                goto="communication_agent"
            )
        
        try:
            self.message_helper.send_video(phone, video_path)
            return Command(
                update={"messages": ["System: Video sent"]},
                goto="communication_agent"
            )
        except Exception as e:
            return Command(
                update={"messages": [f"System: Video could not be sent: {e}"]},
                goto="communication_agent"
            )

    # ================================================================
    # GRAPH SETUP
    # ================================================================

    def build_graph(self):
        """Creates LangGraph workflow"""
        
        graph = StateGraph(UnifiedState)
        
        # Communication nodes
        graph.add_node("communication_agent", self.communication_agent)
        graph.add_node("send_message", self.send_message)
        graph.add_node("wait_user", self.wait_user)
        graph.add_node("choice_persona", self.choice_persona)
        graph.add_node("send_music", self.send_music)
        graph.add_node("send_cover", self.send_cover)
        graph.add_node("send_video", self.send_video)
        
        # Task planning
        graph.add_node("task_planner", self.task_planner)
        
        # Music generation
        graph.add_node("music_generator", self.music_generator)
        graph.add_node("music_selection_prompt", self.music_selection_prompt)
        graph.add_node("music_selection_handler", self.music_selection_handler)
        graph.add_node("music_remake", self.music_remake)
        
        # Cover generation
        graph.add_node("cover_generator", self.cover_generator)
        
        # Video generation
        graph.add_node("video_generator", self.video_generator)
        
        # Delivery
        graph.add_node("delivery_agent", self.delivery_agent)
        
        # Finish
        graph.add_node("finish", self.finish)
        
        # Entry point
        graph.set_entry_point("communication_agent")
        
        # End edge
        graph.add_edge("finish", END)
        
        # Compile with memory and interrupt points
        self.workflow = graph.compile(
            checkpointer=self.memory,
            interrupt_before=["wait_user", "music_selection_handler"]
        )
        
        return self.workflow


# Factory function
def create_system_supervisor():
    supervisor = SystemSupervisor()
    supervisor.build_graph()
    return supervisor