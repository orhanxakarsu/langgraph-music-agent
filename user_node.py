import os
import time
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from dotenv import load_dotenv
from base_models import *
from whatsapp_helper import WhatsApp
from state import UserComminicationState
from personadb_utils import PersonaDB
from langgraph.types import interrupt


load_dotenv()


class UserCommunicationAgent:

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o")
        self.message_helper = WhatsApp()
        self.persona_db = PersonaDB()
        self.memory = MemorySaver()
        self.workflow = None

    def communication_agent(self, state: UserComminicationState):
        """Main communication agent - analyzes messages and decides on action"""
        
        system_message = """You are the user communication manager of a music production company. Your purpose is to analyze the current situation and take action.

# Actions 
- **send_message**: Send an informational message to the user (then wait_user)
- **send_music**: Send the generated music (must be ready)
- **send_cover**: Send the cover image (must be ready)
- **send_video**: Send the video (must be ready)
- **choice_persona**: Show persona list and have them select
- **supervisor**: Redirect to supervisor for music/cover/video generation
- **wait_user**: ONLY wait for user response (don't send message!)
- **finish**: End the process

# IMPORTANT: 
- After sending message to user, MUST go to wait_user
- After wait_user, returns to communication_agent
- Don't use finish unless process is completely done

# Current Status:
- is_music_generated: {is_music_generated}
- is_cover_generated: {is_cover_generated}
- is_video_generated: {is_video_generated}

# Decision Logic:
1. User said hello + nothing generated → send_message (then wait_user)
2. User requested music + not generated → supervisor
3. Music generated + not sent → send_music
4. Need info from user → send_message (then wait_user)
5. Process COMPLETELY done → finish

Communicate naturally and friendly.
"""
        
        human_message = """
# Conversation History:
{messages}

Analyze situation and determine action.
"""

        communication_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        communication_chain = communication_template | self.llm.with_structured_output(
            CommunicationDecisionBaseModel
        )

        result = communication_chain.invoke({
            "messages": state["messages"],
            "is_music_generated": state.get("is_music_generated", False),
            "is_cover_generated": state.get("is_cover_generated", False),
            "is_video_generated": state.get("is_video_remake_generated", False)
        })

        action = result.action
        description = result.description

        print(f"--- Communication Agent Decision: {action.upper()} ---")
        print(f"--- Reason: {description} ---")

        return Command(
            update={
                "action": action,
                "description": description
            },
            goto=action
        )


    def send_message(self, state: UserComminicationState):
        """Sends message to user"""
        
        message_text = state["description"]
        phone = state["phone_number"]
        
        try:
            self.message_helper.send_message(phone, message_text)
            print(f"Message Sent: {phone}")
            
            return Command(
                update={
                    "messages": [f"Assistant: {message_text}"]
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"Message Send Error: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: Message could not be sent - {str(e)}"]
                },
                goto="communication_agent"
            )


    def send_music(self, state: UserComminicationState):
        """Sends generated music to user"""
        
        audio_path = state.get("selected_audio_file_adress")
        description = state["description"]
        phone = state["phone_number"]
        
        if not audio_path:
            return Command(
                update={
                    "messages": ["System: Music file not found"]
                },
                goto="communication_agent"
            )
        
        try:
            # Description first
            if description:
                self.message_helper.send_message(phone, description)
                time.sleep(1)
            
            # Send music
            self.message_helper.send_audio(phone, audio_path)
            print(f"Music Sent: {phone}")
            
            return Command(
                update={
                    "messages": [
                        f"Assistant: {description}",
                        "System: Music sent"
                    ],
                    "is_music_generated": False  # Prevent resending
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"Music Send Error: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: Music could not be sent - {str(e)}"]
                },
                goto="communication_agent"
            )


    def send_cover(self, state: UserComminicationState):
        """Sends song cover to user"""
        
        cover_path = state.get("cover_image_path")
        description = state["description"]
        phone = state["phone_number"]
        
        if not cover_path:
            return Command(
                update={
                    "messages": ["System: Cover image not found"]
                },
                goto="communication_agent"
            )
        
        try:
            if description:
                self.message_helper.send_message(phone, description)
                time.sleep(1)
            
            # Send image - send_image method will be added to WhatsApp helper
            # self.message_helper.send_image(phone, cover_path)
            print(f"Cover Sent: {phone}")
            
            return Command(
                update={
                    "messages": [
                        f"Assistant: {description}",
                        "System: Cover sent"
                    ],
                    "is_cover_generated": False
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"Cover Send Error: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: Cover could not be sent - {str(e)}"]
                },
                goto="communication_agent"
            )


    def send_video(self, state: UserComminicationState):
        """Sends video to user"""
        
        video_path = state.get("video_file_path")
        description = state["description"]
        phone = state["phone_number"]
        
        if not video_path:
            return Command(
                update={
                    "messages": ["System: Video file not found"]
                },
                goto="communication_agent"
            )
        
        try:
            if description:
                self.message_helper.send_message(phone, description)
                time.sleep(1)
            
            self.message_helper.send_video(phone, video_path)
            print(f"Video Sent: {phone}")
            
            return Command(
                update={
                    "messages": [
                        f"Assistant: {description}",
                        "System: Video sent"
                    ],
                    "is_video_remake_generated": False
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"Video Send Error: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: Video could not be sent - {str(e)}"]
                },
                goto="communication_agent"
            )


    def choice_persona(self, state: UserComminicationState):
        """Persona selection - Lists personas from PersonaDB"""
        
        phone = state["phone_number"]
        
        # Get all personas from PersonaDB
        personas = self.persona_db.list_personas()
        
        if not personas:
            message = "No saved personas yet. First, generate music and save a style you like!"
            
            self.message_helper.send_message(phone, message)
            
            return Command(
                update={
                    "messages": [f"Assistant: {message}"]
                },
                goto="communication_agent"
            )
        
        # Format persona list
        persona_list_message = "Saved Personas:\n\n"
        for idx, persona in enumerate(personas, 1):
            persona_list_message += f"{idx}. {persona['name']}\n"
            persona_list_message += f"   {persona['description']}\n\n"
        
        persona_list_message += "\nWhich persona would you like to use? (Send number)"
        
        try:
            self.message_helper.send_message(phone, persona_list_message)
            print("Persona List Sent")
            
            return Command(
                update={
                    "messages": [f"Assistant: {persona_list_message}"],
                    "action": "wait_user",
                    "available_personas": personas
                },
                goto="wait_user"
            )
        except Exception as e:
            return Command(
                update={
                    "messages": [f"System: Persona list could not be sent - {str(e)}"]
                },
                goto="communication_agent"
            )


    

    def wait_user(self, state: UserComminicationState):
        """Human-in-the-loop: Waits for user message"""
        
        print("--- Waiting for User Response (Human-in-the-loop) ---")
        
        # Use interrupt() - this stops the workflow
        user_message = interrupt("Waiting for user response...")
        
        print(f"--- User Response Received: {user_message} ---")
        
        return Command(
            update={
                "messages": [f"User: {user_message}"]
            },
            goto="communication_agent"
        )


    def supervisor_router(self, state: UserComminicationState):
        """Routes to supervisor agent"""
        
        supervisor_request = state["description"]
        
        print(f"--- Routing to Supervisor: {supervisor_request} ---")
        
        # MusicSupervizorAgentSystem will be called here
        # music_result = music_system.workflow.invoke({
        #     "request": supervisor_request,
        #     "phone_number": state["phone_number"]
        # })
        
        return Command(
            update={
                "messages": [f"System: Sent to Supervisor - {supervisor_request}"]
            },
            goto="communication_agent"
        )


    def finish(self, state: UserComminicationState):
        """Ends the process"""
        print("--- Workflow Completed ---")
        return state


    def set_graph(self):
        """Sets up the LangGraph structure"""
        
        graph = StateGraph(UserComminicationState)
        
        # Add nodes
        graph.add_node("communication_agent", self.communication_agent)
        graph.add_node("send_message", self.send_message)
        graph.add_node("send_music", self.send_music)
        graph.add_node("send_cover", self.send_cover)
        graph.add_node("send_video", self.send_video)
        graph.add_node("choice_persona", self.choice_persona)
        graph.add_node("wait_user", self.wait_user)
        graph.add_node("supervisor", self.supervisor_router)
        graph.add_node("finish", self.finish)
        
        # Entry point
        graph.set_entry_point("communication_agent")
        
        # Connect finish to END
        graph.add_edge("finish", END)
        
        # Compile with MemorySaver
        self.workflow = graph.compile(
            checkpointer=self.memory,
            interrupt_before=["wait_user"]
        )
        
        return self.workflow