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
        self.llm = ChatOpenAI(model="gpt-5")
        self.message_helper = WhatsApp()
        self.persona_db = PersonaDB()
        self.memory = MemorySaver()
        self.workflow = None

    def communication_agent(self, state: UserComminicationState):
        """Ana communication agent - mesajları analiz edip aksiyona karar verir"""
        
        system_message = """Sen bir müzik üretim şirketinin kullanıcı ile iletişim sorumlususun. Amacın içinde bulunduğun durumu analiz edip aksiyon almak.

# Aksiyonlar 
- **send_message**: Kullanıcıya bilgilendirme mesajı gönder (sonra wait_user)
- **send_music**: Üretilen müziği gönder (hazır olmalı)
- **send_cover**: Kapak görselini gönder (hazır olmalı)
- **send_video**: Video'yu gönder (hazır olmalı)
- **choice_persona**: Persona listesini göster ve seçim yaptır
- **supervisor**: Müzik/kapak/video üretimi için supervisor'a yönlendir
- **wait_user**: SADECE kullanıcıdan yanıt bekle (mesaj gönderme!)
- **finish**: İşlemi sonlandır

# ÖNEMLI: 
- Kullanıcıya mesaj gönderdikten sonra MUTLAKA wait_user'a git
- wait_user'dan sonra tekrar communication_agent'a dönülür
- İşlem tamamen bitmedikçe finish kullanma

# Mevcut Durum:
- is_music_generated: {is_music_generated}
- is_cover_generated: {is_cover_generated}
- is_video_generated: {is_video_generated}

# Karar Mantığı:
1. Kullanıcı merhaba dedi + hiçbir şey üretilmedi → send_message (sonra wait_user)
2. Kullanıcı müzik istedi + üretilmemiş → supervisor
3. Müzik üretildi + gönderilmemiş → send_music
4. Kullanıcıdan bilgi gerekli → send_message (sonra wait_user)
5. İşlem TAMAMEN tamam → finish

Doğal ve samimi iletişim kur.
"""
        
        human_message = """
# Konuşma Geçmişi:
{messages}

Durum analizi yap ve aksiyon belirle.
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
        """Kullanıcıya mesaj gönderir"""
        
        message_text = state["description"]
        phone = state["phone_number"]  # 🔥 Direkt state'ten al
        
        try:
            self.message_helper.send_message(phone, message_text)
            print(f"✅ Mesaj Gönderildi: {phone}")
            
            return Command(
                update={
                    "messages": [f"Assistant: {message_text}"]
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"❌ Mesaj Gönderme Hatası: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: Mesaj gönderilemedi - {str(e)}"]
                },
                goto="communication_agent"
            )


    def send_music(self, state: UserComminicationState):
        """Üretilen müziği kullanıcıya gönderir"""
        
        audio_path = state.get("selected_audio_file_adress")
        description = state["description"]
        phone = state["phone_number"]  # 🔥 Direkt state'ten al
        
        if not audio_path:
            return Command(
                update={
                    "messages": ["System: ❌ Müzik dosyası bulunamadı"]
                },
                goto="communication_agent"
            )
        
        try:
            # Önce açıklama
            if description:
                self.message_helper.send_message(phone, description)
                time.sleep(1)
            
            # Müzik gönder
            self.message_helper.send_audio(phone, audio_path)
            print(f"✅ Müzik Gönderildi: {phone}")
            
            return Command(
                update={
                    "messages": [
                        f"Assistant: {description}",
                        "System: 🎵 Müzik gönderildi"
                    ],
                    "is_music_generated": False  # Tekrar gönderme
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"❌ Müzik Gönderme Hatası: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: ❌ Müzik gönderilemedi - {str(e)}"]
                },
                goto="communication_agent"
            )


    def send_cover(self, state: UserComminicationState):
        """Şarkı kapağını kullanıcıya gönderir"""
        
        cover_path = state.get("cover_image_path")
        description = state["description"]
        phone = state["phone_number"]  # 🔥 Direkt state'ten al
        
        if not cover_path:
            return Command(
                update={
                    "messages": ["System: ❌ Kapak görseli bulunamadı"]
                },
                goto="communication_agent"
            )
        
        try:
            if description:
                self.message_helper.send_message(phone, description)
                time.sleep(1)
            
            # Görseli gönder - WhatsApp helper'a send_image metodu eklenecek
            # self.message_helper.send_image(phone, cover_path)
            print(f"✅ Kapak Gönderildi: {phone}")
            
            return Command(
                update={
                    "messages": [
                        f"Assistant: {description}",
                        "System: 🖼️ Kapak gönderildi"
                    ],
                    "is_cover_generated": False
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"❌ Kapak Gönderme Hatası: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: ❌ Kapak gönderilemedi - {str(e)}"]
                },
                goto="communication_agent"
            )


    def send_video(self, state: UserComminicationState):
        """Video'yu kullanıcıya gönderir"""
        
        video_path = state.get("video_file_path")
        description = state["description"]
        phone = state["phone_number"]  # 🔥 Direkt state'ten al
        
        if not video_path:
            return Command(
                update={
                    "messages": ["System: ❌ Video dosyası bulunamadı"]
                },
                goto="communication_agent"
            )
        
        try:
            if description:
                self.message_helper.send_message(phone, description)
                time.sleep(1)
            
            self.message_helper.send_video(phone, video_path)
            print(f"✅ Video Gönderildi: {phone}")
            
            return Command(
                update={
                    "messages": [
                        f"Assistant: {description}",
                        "System: 🎬 Video gönderildi"
                    ],
                    "is_video_remake_generated": False
                },
                goto="communication_agent"
            )
        except Exception as e:
            print(f"❌ Video Gönderme Hatası: {str(e)}")
            return Command(
                update={
                    "messages": [f"System: ❌ Video gönderilemedi - {str(e)}"]
                },
                goto="communication_agent"
            )


    def choice_persona(self, state: UserComminicationState):
        """Persona seçimi - PersonaDB'den personaları listeler"""
        
        phone = state["phone_number"]  # 🔥 Direkt state'ten al
        
        # PersonaDB'den tüm personaları çek
        personas = self.persona_db.list_personas()
        
        if not personas:
            message = "❌ Henüz kaydedilmiş persona yok. Önce bir müzik üretip beğendiğin tarzı kaydetmelisin!"
            
            self.message_helper.send_message(phone, message)
            
            return Command(
                update={
                    "messages": [f"Assistant: {message}"]
                },
                goto="communication_agent"
            )
        
        # Persona listesini formatla
        persona_list_message = "🎭 Kayıtlı Personalar:\n\n"
        for idx, persona in enumerate(personas, 1):
            persona_list_message += f"{idx}. {persona['name']}\n"
            persona_list_message += f"   📝 {persona['description']}\n\n"
        
        persona_list_message += "\nHangi personayı kullanmak istersin? (Numara gönder)"
        
        try:
            self.message_helper.send_message(phone, persona_list_message)
            print("✅ Persona Listesi Gönderildi")
            
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
                    "messages": [f"System: ❌ Persona listesi gönderilemedi - {str(e)}"]
                },
                goto="communication_agent"
            )


    

    def wait_user(self, state: UserComminicationState):
        """Human-in-the-loop: Kullanıcı mesajı bekler"""
        
        print("--- 🛑 Kullanıcı Yanıtı Bekleniyor (Human-in-the-loop) ---")
        
        # 🔥 interrupt() kullan - bu workflow'u durdurur
        user_message = interrupt("Waiting for user response...")
        
        print(f"--- ✅ Kullanıcı Yanıtı Alındı: {user_message} ---")
        
        return Command(
            update={
                "messages": [f"User: {user_message}"]
            },
            goto="communication_agent"
        )


    def supervisor_router(self, state: UserComminicationState):
        """Supervisor agent'e yönlendirme yapar"""
        
        supervisor_request = state["description"]
        
        print(f"--- 📤 Supervisor'a Yönlendiriliyor: {supervisor_request} ---")
        
        # Burada MusicSupervizorAgentSystem çağrılacak
        # music_result = music_system.workflow.invoke({
        #     "request": supervisor_request,
        #     "phone_number": state["phone_number"]
        # })
        
        return Command(
            update={
                "messages": [f"System: 📤 Supervisor'a iletildi - {supervisor_request}"]
            },
            goto="communication_agent"
        )


    def finish(self, state: UserComminicationState):
        """İşlemi sonlandırır"""
        print("--- Workflow Tamamlandı ---")
        return state


    def set_graph(self):
        """LangGraph yapısını kurar"""
        
        graph = StateGraph(UserComminicationState)
        
        # Node'ları ekle
        graph.add_node("communication_agent", self.communication_agent)
        graph.add_node("send_message", self.send_message)
        graph.add_node("send_music", self.send_music)
        graph.add_node("send_cover", self.send_cover)
        graph.add_node("send_video", self.send_video)
        graph.add_node("choice_persona", self.choice_persona)
        graph.add_node("wait_user", self.wait_user)
        graph.add_node("supervisor", self.supervisor_router)
        graph.add_node("finish", self.finish)
        
        # Başlangıç
        graph.set_entry_point("communication_agent")
        
        # Finish'i END'e bağla
        graph.add_edge("finish", END)
        
        # MemorySaver ile compile
        self.workflow = graph.compile(
            checkpointer=self.memory,
            interrupt_before=["wait_user"]
        )
        
        return self.workflow