import os
import os
import requests
import time
import uuid
from database import PersonaDB
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import Optional, Literal, Annotated
from flask import Flask, request, jsonify, send_from_directory
from langgraph.graph import StateGraph, END, add_messages
from database import PersonaDB
from state import MusicGenerationState
from langgraph.types import Command
from personadb_utils import PersonaDB
class MusicGenerationAgentBaseModel(BaseModel):

    next: Literal["generate_music", "persona_saver", "remake_music"] = Field(...,description = "Sonraki adımın ne olduğu bilgisi.")
    # Düşünme bu şekilde ileri doğru sürekli devam eder.
    reason: str = Field(..., "Bu kararı neden aldığının gerekçesi")
    request_detail: str = Field("Gelen isteğin sıradaki yapıya verilecek detaylı açıklaması")


class MusicSupervizorAgentSystem:

    def __init__(self):
        self.llm= ChatOpenAI(model = "gpt-5")
    

    def supervisor_agent(self,state: MusicGenerationState):
        system_message = """Sen bir müzik üretim uzmanısın. Gelen isteğe göre hangi aracı kullanacağını seçeceksin.

        generate_music: Eğer müzik üretmekle alakalı bir istek geldiyse, **generate_music**
        persona_saver: Eğer kullanıcı yapmış olduğun şarkının personasını beğendiyse, bu yapı mevcut üretilen şarkının personasını kaydeder. Eğer buna uygun bir istem gelirse bu endpoint'i kullan.
        remake_music: Eğer kullanıcı üretilen müziği beğenmediyse ya da yeniden üretilmesini söylerse, sözleri beğenmediyse **remake_music** yapısına yönlendirilir. Burada parça yeniden yapılır.

        Bu kararları aldıktan sonra neden bu kararı aldığının açıklamasını **reason** kısmına yazmanı istiyorum.
        
        Seçilmiş bir şarkı bilgisi var mı yok mu onu sana vereceğim. Eğer seçilmiş bir şarkı yoksa ve ilk defa çalışacaksan remake_music ve persona_saver adreslerine yönlendiremezsin. 

        Seçilmiş Şarkı: True or False
        
        """
    
        human_message = """İstek : {istek}.
        
        Seçilmiş Şarkı: {is_generated}
        Senden bu isteğe göre düzgün bir karar alman bekleniyor.
        """

        supervisor_template = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                ("human",human_message)
            ]
        )


        supervisor_chain = supervisor_template | self.llm.structured_output(MusicGenerationAgentBaseModel)

        response = supervisor_chain.invoke({
            "istek": state["request"],
            "is_generated": False if len(state["generated_audio_urls"]) ==
        })

        goto = response.next
        request_detail = response.request_detail

        if goto == "persona_saver":
            if len(state["generated_audio_urls"]) == 0:
                print("Henüz Üretilmiş Bir Şarkı Yok")

        print(f"--- Musif Generation Workflow Transition: Router -> {goto.upper()} ---")

        return Command(
            update = {
                "step_list": [goto],
                "request_details_from_supervisor" : [request_detail]
            },
            goto=goto
        )


    def persona_saver(self, state: MusicGenerationState):
        """ Müziğin kişiliğini değiştiren ya da müziğe yeni bir kişilik, tarz ekleyen sistem."""

        system_message = """Sen müziğin personasını kaydetme uzmanısın. 
        
        


        
        """
        



class PersonaChangerBaseModel(BaseModel):
    name: Optional[str] = Field(...,description = "Personanın kişiliğini yansıtan ismi (Örnek: Electronic Pop Singer)")
    description: Optional[str] = Field(...,description = "Personanın kişilik açıklaması ")
    selected_persona :Optional[str] = Field(..., description = "Eğer mevcutta olan personalardan biri seçildiyse onun açıklaması")




