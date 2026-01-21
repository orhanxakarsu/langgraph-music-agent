import os
import requests
import time
import uuid
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from flask import Flask, request, jsonify, send_from_directory
from langgraph.graph import StateGraph, END, add_messages
from state import MusicGenerationState
from langgraph.types import Command
from dotenv import load_dotenv
from base_models import *
from suno_ai import SunoAPI

# Request comes to music supervisor ->
# Supervisor decides whether to generate music, revise existing music, or save the persona of current music.
# Task completes and returns to system supervisor.


load_dotenv()


class MusicSupervizorAgentSystem:

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o")
        self.suno_api = SunoAPI()
    

    def supervisor_agent(self, state: MusicGenerationState):
        system_message = """You are a music production expert. You will select which tool to use based on the incoming request.

        generate_music: If the request is about generating music, use **generate_music**
        persona_saver: If the user liked the persona of the song you created, this saves the current song's persona. Use this endpoint if a matching request comes.
        remake_music: If the user didn't like the generated music or wants it regenerated, or didn't like the lyrics, redirect to **remake_music**. The track will be remade here.
        return: If there's no task to do, the task definition is wrong, there's missing context, or no song is selected but persona generation is requested, redirect to **return**.
        
        After making these decisions, I want you to write the explanation of why you made this decision in the **reason** field.
        
        I will tell you whether there's a selected song or not. If there's no selected song and this is the first run, you cannot redirect to remake_music and persona_saver.

        Selected Song: True or False
        
        ### Fill reason as follows:
        - If going to generate_music, description of the music to be generated
        - If going to remake_music, detailed information about how the music will change.

        """
    
        human_message = """Request: {request}.
        
        Selected Song: {is_generated}
        You are expected to make a proper decision based on this request.
        """

        supervisor_template = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                ("human", human_message)
            ]
        )


        supervisor_chain = supervisor_template | self.llm.with_structured_output(MusicGenerationAgentBaseModel)

        response = supervisor_chain.invoke({
            "request": state["request"],
            "is_generated": True if state.get("selected_audio_url", None) else False
        })


        goto = response.next
        request_detail = response.request_detail


        if goto == "persona_saver":
            if len(state["generated_audio_urls"]) == 0:
                print("No song has been generated yet")
                return None


        if goto == "return":
            print("MusicSupervisor could not find a decision to make. Returning.")
            print(request_detail)
            return {
                "request_details_from_supervisor": request_detail
            }


        print(f"--- Music Generation Workflow Transition: Router -> {goto.upper()} ---")

        return Command(
            update={
                "step_list": [goto],
                "request_details_from_supervisor": [request_detail]
            },
            goto=goto
        )


    def generate_music(self, state: MusicGenerationState):
        """Generates new music. Processes instructions from Supervisor with LLM."""
        
        system_message = """You are a professional music creation expert. Create a detailed music generation template according to the given instructions. The properties of the outputs I want from you are as follows:
        ## IF WRITING A SONG WITH LYRICS, ONLY THE LYRICS SHOULD BE IN THE PROMPT.
        ## WRITE ALL OTHER INSTRUCTIONS IN ENGLISH. ONLY THE LYRICS IN THE PROMPT SHOULD BE IN THAT LANGUAGE.
        ## Don't hesitate to use negative_tags. You can remove elements that don't fit the context.
        
        - custom_mode: Enables Custom Mode for advanced audio creation settings.
            * Set to *True* to use custom mode (style and title required; if instrumental = True, prompt is only used as lyrics.)
            * Set to False if custom mode is not wanted (only prompt required, lyrics will be auto-set according to prompt.)
        
        - instrumental: Determines whether the audio is instrumental (no vocals).
            * In custom mode (custom_mode = True) only style and title are sufficient, no prompt needed.
            * (custom_mode = False) Has no effect on required fields (just prompt). If instrumental = False, lyrics are auto-generated in non-custom mode.

        
        - prompt: Description of desired audio content
            * In Custom Mode (custom_mode = True) required if instrumental = False. Prompt will be used as the song's lyrics. The lyrics will be created from the prompt content.
            * **Must be maximum 3000 characters.**
            * In Non-Custom Mode (custom_mode = False) always required. Prompt serves as the basic idea and lyrics are auto-generated accordingly (won't match prompt content exactly). Maximum 500 characters.

            # Think like a professional when writing lyrics. Pay attention to rhymes and impactful words that will captivate people and make them listen to the music.
            

        - style: Music style or genre for the audio
            * Required in Custom Mode (custom_mode=True). Examples: "Jazz", "Classical", "Electronic."
            * Leave empty in Non-Custom Mode (custom_mode=False).
            **Maximum size: 200 characters**
        
        - title: Title of the generated music piece
            * Required in Custom Mode (custom_mode=True). Maximum length 80 characters (Example: Peaceful Piano Meditation)
            * Leave empty in Non-Custom Mode (custom_mode = False).

        - negative_tags: Music styles or characteristics to exclude from generated audio
            * Optional. Use to prevent specific styles. Can be empty string if nothing to add.
            Example: "Heavy Metal, Upbeat Drums"
        
        - vocal_gender: Preferred vocal gender in generated vocals. (m: male, f: female) (can only be f or m.)

        - style_weight: Weight of provided style guidance (Range 0 to 1)

        - weirdness_constraint: Constraint on creative deviation/novelty (Range 0 to 1)

        - audio_weight: Weight of input audio (when applicable) (Range 0 to 1)

        
        You are expected to generate a detailed and complete music generation guide suitable for the given task. Apply the instructions and pay attention to character limits.
        """
        
        human_message = """Instruction: {request_detail}
        
        
        Generate music production parameters according to this instruction."""
        
        generate_music_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])
        
        generate_music_chain = generate_music_template | self.llm.with_structured_output(MusicBaseModel)
        
        result = generate_music_chain.invoke({
            "request_detail": state["request_details_from_supervisor"][-1],
        })
        

        # Call SunoAPI
        api_result = self.suno_api.create_music(state, music_params=result)
        
        # Node should return its own state update
        if api_result["is_generated"]:
            api_result = api_result["current_state"]
            return {
                "generated_audio_ids": api_result["generated_audio_ids"],
                "generated_audio_urls": api_result["generated_audio_urls"],
                "generated_audio_file_adress": api_result["generated_audio_file_adress"],
                "is_generated": True,
                "step_list": state["step_list"] + ["generate_music"]
            }
        else:
            return {
                "is_generated": False,
                "error_message": api_result.get("error", "Unknown error")
            }




    def persona_saver(self, state: MusicGenerationState):
        """System that changes or adds a new personality/style to the music."""

        system_message = """You are a music persona saving expert. If the user is using you, they liked the previously generated song. From the given information:
        persona_name: Name of the persona to be created (Short persona content e.g.: Electronic Pop Singer)
        description: Description of the persona to be created (Important for persona, can also change based on these guidelines e.g.: A modern electronic music style pop singer, skilled in dynamic rhythms and synthesizer tones)
        """
        
        human_message = """
        The properties of the track whose persona I want you to save:

        prompt used to generate music: {prompt}
        
        style used to generate music: {style}
        
        title used to generate music: {title}

        instrumental: {instrumental} (True means no vocals in the track, False means it has lyrics)

        Unwanted characteristics in music: {negative_tags}
        
        Persona's gender: {vocal_gender}

        Weight of entered style on the track: {style_weight}
        
        Create name and description based on this given information.
        """


        persona_saver_template = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                ("human", human_message)
            ]
        )

        persona_saver_chain = persona_saver_template | self.llm.with_structured_output(PersonaChangerBaseModel)

        result = persona_saver_chain.invoke(
            {
                "prompt": state["prompt"],
                "style": state["style"],
                "title": state["title"],
                "instrumental": state["instrumental"],
                "vocal_gender": state["vocal_gender"],
                "negative_tags": state["negative_tags"],
                "style_weight": state["style_weight"]
            }
        )

        state["persona_saver_name"] = result.name
        state["persona_saver_description"] = result.description

        state = self.suno_api.create_and_save_persona(state=state)

        if state["is_persona_saved"]:
            print("--- Persona Successfully Created and Saved ---")
        
        else:
            print("--- Error in Persona Creation and Saving! ---")

        return {
            "persona_saver_name": state["persona_saver_name"],
            "persona_saver_description": state["persona_saver_description"],
            "created_persona_id": state["created_persona_id"]
        }
    
                  


    def remake_music(self, state: MusicGenerationState):
        """Transforms a track into a new style while preserving the core melody."""


        system_message = """You are a music recreation expert. Expand the music recreation based on the incoming request.
        Your task is to transform a track into a new style while preserving the core melody.
        Persona change may be requested; if so, fill in the relevant field in the template accordingly.

        prompt: Detailed instruction for the music you're changing, write what you want not what's changing.
        style: Enter the new music's style here (e.g.: Classical)
        title: New Music's Title (e.g.: Peaceful Piano Meditation)
        instrumental: True if new music will be without vocals, False if it will have lyrics
        negative_tags: Enter components you don't want in the song (e.g.: Heavy Metal, Upbeat Drums)
        vocal_gender: Gender of the new track's vocalist (f: female, m: male ONLY f OR m)
        style_weight: Weight of provided style guidance (0 to 1)
        weirdness_constraint: Constraint on creative deviation/novelty (0 to 1)
        audio_weight: Weight of input audio (when applicable) (0 to 1)
        
        """

        human_message = """You are asked to make changes based on this request:
        Request: {request}
        """


        remake_music_template = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                ("human", human_message)
            ]
        )

        remake_music_chain = remake_music_template | self.llm.with_structured_output(MusicBaseModel)

        result = remake_music_chain.invoke({
            "request": state["request_details_from_supervisor"]
        })




    def set_graph(self):
        """Sets up the LangGraph structure."""
        
        graph = StateGraph(MusicGenerationState)
        
        # Add nodes
        graph.add_node("supervisor", self.supervisor_agent)
        graph.add_node("generate_music", self.generate_music)
        graph.add_node("persona_saver", self.persona_saver)
        graph.add_node("remake_music", self.remake_music)
        
        # Entry point
        graph.set_entry_point("supervisor")
        
        # Supervisor goes via Command (goto auto-routes)
        # Other nodes go to END when finished
        graph.add_edge("generate_music", END)
        graph.add_edge("persona_saver", END)
        graph.add_edge("remake_music", END)
        
        # Compile
        self.workflow = graph.compile()
        
        return self.workflow


        
agent = MusicSupervizorAgentSystem()

flow = agent.set_graph()

result = flow.invoke({
    "request": "Can you create a detailed and beautiful instrumental music combining medieval Turkish songs (kopuz, throat singing etc) with ancient Anatolian celtic melodies"
})


