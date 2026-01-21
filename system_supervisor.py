"""
System Supervisor Agent
=======================
Tüm sistemin beyni. Kullanıcı iletişimini, görev planlamasını ve 
tüm alt agent'ları koordine eder.

Akış:
1. communication_agent: Kullanıcı mesajını anlar
2. task_planner: Görevleri planlar
3. music_generator: Müzik üretir
4. music_selection_handler: Müzik seçimi
5. cover_generator: Kapak üretir
6. video_generator: Video üretir
7. delivery_agent: Sonuçları teslim eder
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
    Mesaj listesini string'e çevirir.
    HumanMessage, AIMessage veya string olabilir.
    """
    result = []
    for msg in messages[-last_n:]:
        if isinstance(msg, str):
            result.append(msg)
        elif hasattr(msg, 'content'):
            # HumanMessage, AIMessage, SystemMessage vs.
            role = msg.__class__.__name__.replace("Message", "")
            result.append(f"{role}: {msg.content}")
        else:
            result.append(str(msg))
    return "\n".join(result)


class SystemSupervisor:
    """
    Tüm sistemi yöneten ana supervisor.
    Tek bir workflow içinde tüm agent'ları koordine eder.
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
        Ana iletişim agent'ı - kullanıcı mesajını analiz eder ve aksiyon belirler.
        """
        
        system_message = """Sen bir müzik üretim şirketinin akıllı asistanısın. 
Kullanıcıyla WhatsApp üzerinden iletişim kuruyorsun.

# GÖREVLER:
1. Kullanıcının ne istediğini anla
2. Uygun aksiyonu seç
3. Doğal ve samimi iletişim kur

# AKSİYONLAR:
- **task_planner**: Yeni bir üretim görevi var (müzik/kapak/video üret)
- **send_message**: Bilgilendirme mesajı gönder, sonra cevap bekle
- **send_music**: Hazır müziği gönder
- **send_cover**: Hazır kapak görselini gönder  
- **send_video**: Hazır videoyu gönder
- **choice_persona**: Persona listesini göster
- **wait_user**: Kullanıcıdan yanıt bekle
- **finish**: Konuşmayı sonlandır

# MEVCUT DURUM:
- Stage: {current_stage}
- Müzik üretildi mi: {is_music_generated}
- Müzik seçildi mi: {is_music_selected}
- Kapak üretildi mi: {is_cover_generated}
- Video üretildi mi: {is_video_generated}
- Görev kuyruğu: {task_queue}
- Tamamlanan görevler: {completed_tasks}

# KARAR MANTIĞI:
1. Kullanıcı yeni bir şey istiyorsa → task_planner
2. Müzik hazır ama gönderilmemişse → send_music
3. Kapak hazır ama gönderilmemişse → send_cover
4. Video hazır ama gönderilmemişse → send_video
5. Soru sorduysan → wait_user
6. Her şey tamam ve kullanıcı memnun → finish

# ÖNEMLİ:
- Mesaj gönderdikten sonra wait_user'a git
- Kullanıcıdan bilgi lazımsa önce sor
- Samimi ve yardımsever ol
- HATA DURUMU varsa ve deneme sayısı 2'ye ulaştıysa task_planner'a GİTME, kullanıcıya özür dile ve wait_user'a git
- Aynı görev için sürekli task_planner'a gitme (hata döngüsü oluşur)
"""
        
        human_message = """
# Son Mesajlar:
{messages}

# Hata Durumu:
{error_info}

Durumu analiz et ve aksiyon belirle.
"""

        template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])

        chain = template | self.llm.with_structured_output(CommunicationDecisionBaseModel)

        # Hata bilgisi
        error_info = "Yok"
        if state.get("error_message"):
            retry = state.get("retry_count", 0)
            error_info = f"Hata: {state['error_message']} (Deneme: {retry}/2)"

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
        print(f"🤖 COMMUNICATION AGENT")
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
        """Kullanıcıya mesaj gönderir"""
        
        message = state.get("communication_description", "")
        phone = state["phone_number"]
        
        try:
            self.message_helper.send_message(phone, message)
            print(f"✅ Mesaj gönderildi: {phone}")
            
            return Command(
                update={
                    "messages": [f"Assistant: {message}"]
                },
                goto="wait_user"
            )
        except Exception as e:
            print(f"❌ Mesaj hatası: {e}")
            return Command(
                update={
                    "messages": [f"System: Mesaj gönderilemedi - {e}"],
                    "error_message": str(e)
                },
                goto="communication_agent"
            )

    def wait_user(self, state: UnifiedState):
        """Human-in-the-loop: Kullanıcı yanıtı bekler"""
        
        print("\n⏳ Kullanıcı yanıtı bekleniyor...")
        
        user_response = interrupt("Waiting for user response...")
        
        print(f"✅ Kullanıcı yanıtı: {user_response}")
        
        return Command(
            update={
                "messages": [f"User: {user_response}"],
                "user_request": user_response
            },
            goto="communication_agent"
        )

    def choice_persona(self, state: UnifiedState):
        """Persona seçimi"""
        
        phone = state["phone_number"]
        personas = self.persona_db.list_personas()
        
        if not personas:
            message = "❌ Henüz kayıtlı persona yok. Önce bir müzik üretip beğendiğin tarzı kaydetmelisin!"
            self.message_helper.send_message(phone, message)
            
            return Command(
                update={"messages": [f"Assistant: {message}"]},
                goto="wait_user"
            )
        
        # Persona listesini formatla
        message = "🎭 Kayıtlı Personalar:\n\n"
        for idx, persona in enumerate(personas, 1):
            message += f"{idx}. {persona['name']}\n"
            message += f"   📝 {persona.get('description', 'Açıklama yok')}\n\n"
        message += "\nHangi personayı kullanmak istersin? (Numara gönder)"
        
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
        Görev planlayıcı - kullanıcının isteğini analiz eder ve 
        yapılacak görevleri belirler.
        """
        
        system_message = """Sen bir müzik prodüksiyon planlayıcısısın.
Kullanıcının isteğini analiz edip hangi görevlerin yapılacağını belirle.

# GÖREVLER:
- **music**: Yeni müzik üret
- **cover**: Albüm/şarkı kapağı üret
- **video**: Müzik videosu oluştur (müzik + kapak birleşimi)
- **persona_save**: Mevcut müziğin tarzını kaydet
- **remake**: Mevcut müziği yeniden üret/düzenle

# KURALLAR:
1. Video için önce müzik VE kapak gerekli
2. Remake için önce bir müzik üretilmiş olmalı
3. Persona kaydetmek için seçilmiş bir müzik olmalı
4. Görevleri mantıklı sıraya koy: music → cover → video

# MEVCUT DURUM:
- Müzik var mı: {has_music}
- Seçilmiş müzik var mı: {has_selected_music}
- Kapak var mı: {has_cover}

Kullanıcının isteğine göre görevleri planla.
"""

        human_message = """
Kullanıcı isteği: {user_request}

Son mesajlar:
{recent_messages}

Görevleri planla ve kullanıcıya bilgilendirici bir mesaj hazırla.
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
        print(f"📋 TASK PLANNER")
        print(f"   Tasks: {result.tasks}")
        print(f"   Music desc: {result.music_description}")
        print(f"   Cover desc: {result.cover_description}")
        print(f"{'='*50}\n")

        # Kullanıcıya bilgi ver
        phone = state["phone_number"]
        self.message_helper.send_message(phone, result.response_to_user)

        # İlk görevi belirle
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
        """Müzik üretir - Suno API kullanır"""
        
        print("\n🎵 MUSIC GENERATOR başladı...")
        
        # Retry kontrolü - max 2 deneme
        retry_count = state.get("retry_count", 0)
        if retry_count >= 2:
            print(f"   ❌ Maksimum deneme sayısına ulaşıldı ({retry_count})")
            
            # Kullanıcıya hata mesajı gönder
            phone = state["phone_number"]
            self.message_helper.send_message(
                phone,
                "😔 Müzik üretiminde sorun yaşıyorum. Lütfen biraz sonra tekrar dene veya farklı bir istek yap."
            )
            
            return Command(
                update={
                    "error_message": "Max retry exceeded",
                    "current_stage": "idle",
                    "retry_count": 0,  # Sıfırla
                    "task_queue": [],
                    "messages": ["System: ❌ Müzik üretimi başarısız - max retry"]
                },
                goto="wait_user"
            )
        
        system_message = """Sen profesyonel bir müzik yaratma uzmanısın.

# KURALLAR:
- custom_mode: True (gelişmiş ayarlar için)
- instrumental: True ise sözsüz, False ise sözlü
- prompt: Şarkı sözleri (max 3000 karakter) - SÖZLÜ ise şarkı sözlerini yaz
- style: Müzik stili (max 200 karakter)
- title: Başlık (max 80 karakter)
- Tüm yönergeler İNGİLİZCE olsun, sadece şarkı sözleri istenen dilde

# ÖNEMLİ:
- Şarkı sözleri yazarken kafiyelere dikkat et
- Minimalist ama etkileyici ol
- negative_tags ile istenmeyen unsurları belirt
"""

        human_message = """
Müzik talebi: {music_description}

Bu talebe uygun detaylı müzik parametreleri oluştur.
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

        # Suno API çağrısı
        api_result = self.suno_api.create_music(state, music_params)

        if api_result["is_generated"]:
            updated_state = api_result["current_state"]
            
            # None değerleri filtrele
            audio_paths = [p for p in updated_state.get("generated_audio_file_adress", []) if p]
            audio_ids = updated_state.get("generated_audio_ids", [])
            audio_urls = updated_state.get("generated_audio_urls", [])
            
            print(f"   ✅ Müzik üretildi!")
            print(f"   Audio IDs: {audio_ids}")
            print(f"   Downloaded paths: {audio_paths}")
            
            # Hiç indirilen müzik yoksa hata
            if not audio_paths:
                print("   ❌ Müzikler indirilemedi!")
                return Command(
                    update={
                        "error_message": "Müzikler indirilemedi",
                        "last_error_stage": "music_generator",
                        "retry_count": retry_count + 1,
                        "messages": [f"System: ❌ Müzikler indirilemedi (deneme {retry_count + 1})"]
                    },
                    goto="communication_agent"
                )
            
            # Görev kuyruğunu güncelle
            remaining_tasks = state.get("task_queue", [])[1:]  # İlk görevi çıkar
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
                    "retry_count": 0,  # Başarılı - sıfırla
                    "messages": [f"System: 🎵 {len(audio_paths)} müzik üretildi, seçim bekleniyor"]
                },
                goto="music_selection_prompt"
            )
        else:
            print(f"   ❌ Müzik üretilemedi!")
            return Command(
                update={
                    "error_message": api_result.get("error", "Müzik üretilemedi"),
                    "last_error_stage": "music_generator",
                    "retry_count": retry_count + 1,  # Retry sayısını artır
                    "messages": [f"System: ❌ Müzik üretiminde hata (deneme {retry_count + 1})"]
                },
                goto="communication_agent"
            )

    def music_selection_prompt(self, state: UnifiedState):
        """Kullanıcıya 2 müziği link olarak gönderir ve seçim yapmasını ister"""
        
        phone = state["phone_number"]
        audio_paths = state.get("generated_audio_file_paths", [])
        
        # None değerleri filtrele
        audio_paths = [p for p in audio_paths if p]
        
        print(f"\n🎵 MUSIC SELECTION - {len(audio_paths)} müzik linki gönderiliyor...")
        
        if not audio_paths:
            print("   ❌ İndirilmiş müzik yok!")
            self.message_helper.send_message(
                phone,
                "😔 Müzikler indirilemedi. Biraz bekleyip tekrar deneyelim mi?"
            )
            return Command(
                update={
                    "messages": ["System: ❌ Müzik dosyaları bulunamadı"],
                    "current_stage": "idle"
                },
                goto="wait_user"
            )
        
        # Açıklama mesajı
        message = "🎵 Sana 2 farklı versiyon ürettim!\n\n"
        message += "Seçeneklerin:\n"
        message += "• '1' veya '2' - Birini seç\n"
        message += "• 'ikisi de' - Her ikisini de kullan\n"
        message += "• 'hiçbiri' - Yeniden üret\n"
        message += "• Geri bildirim yaz - Ne değişmesini istediğini söyle"
        
        self.message_helper.send_message(phone, message)
        time.sleep(1)
        
        # Müzik linklerini AYRI AYRI mesaj olarak gönder (tıklanabilir olması için)
        for idx, audio_path in enumerate(audio_paths[:2], 1):
            try:
                # URL oluştur
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(audio_path)
                else:
                    # Fallback: dosya adından URL oluştur
                    filename = os.path.basename(audio_path)
                    file_url = f"http://localhost:5000/files/music/{filename}"
                
                # Her linki ayrı mesajda gönder
                link_message = f"🎵 Versiyon {idx}:\n{file_url}"
                self.message_helper.send_message(phone, link_message)
                time.sleep(2)  # WhatsApp rate limit için bekle
                
                print(f"   ✅ Müzik {idx} linki gönderildi: {file_url}")
            except Exception as e:
                print(f"   ❌ Müzik {idx} linki gönderilemedi: {e}")
        
        return Command(
            update={
                "messages": [f"Assistant: {message}", "System: 🎵 Müzik linkleri gönderildi"],
                "current_stage": "awaiting_music_selection"
            },
            goto="music_selection_handler"
        )

    def music_selection_handler(self, state: UnifiedState):
        """Kullanıcının müzik seçimini bekler ve işler"""
        
        print("\n⏳ Müzik seçimi bekleniyor...")
        
        user_response = interrupt("Waiting for music selection...")
        
        print(f"✅ Kullanıcı yanıtı: {user_response}")
        
        # Yanıtı analiz et
        response_lower = user_response.lower().strip()
        
        audio_ids = state.get("generated_audio_ids", [])
        audio_urls = state.get("generated_audio_urls", [])
        audio_paths = state.get("generated_audio_file_paths", [])
        
        selected_index = None
        next_node = "communication_agent"
        updates = {"messages": [f"User: {user_response}"]}
        
        if response_lower in ["1", "bir", "birinci", "ilk"]:
            selected_index = 0
            updates["messages"].append("System: Birinci müzik seçildi")
            
        elif response_lower in ["2", "iki", "ikinci"]:
            selected_index = 1
            updates["messages"].append("System: İkinci müzik seçildi")
            
        elif "ikisi" in response_lower or "her iki" in response_lower:
            # İkisini de seç (ilkini ana olarak kullan)
            selected_index = 0
            updates["messages"].append("System: Her iki müzik de kabul edildi, birincisi kullanılacak")
            
        elif "hiçbiri" in response_lower or "yeniden" in response_lower or "tekrar" in response_lower:
            # Remake iste
            updates["is_remake_requested"] = True
            updates["remake_instructions"] = user_response
            updates["current_stage"] = "generating_music"
            updates["messages"].append("System: Müzik yeniden üretilecek")
            next_node = "music_generator"
            
        else:
            # Geri bildirim olarak değerlendir - remake yap
            updates["is_remake_requested"] = True
            updates["remake_instructions"] = user_response
            updates["current_stage"] = "generating_music"
            updates["messages"].append(f"System: Geri bildirime göre yeniden üretilecek: {user_response}")
            next_node = "music_generator"
        
        # Seçim yapıldıysa state'i güncelle
        if selected_index is not None:
            updates["selected_audio_index"] = selected_index
            updates["selected_audio_id"] = audio_ids[selected_index] if audio_ids else None
            updates["selected_audio_url"] = audio_urls[selected_index] if audio_urls else None
            updates["selected_audio_file_path"] = audio_paths[selected_index] if audio_paths else None
            updates["is_music_selected"] = True
            updates["current_stage"] = "generating_cover" if "cover" in state.get("task_queue", []) else "delivering"
            
            # Sonraki göreve geç
            if "cover" in state.get("task_queue", []):
                next_node = "cover_generator"
            else:
                next_node = "delivery_agent"
        
        return Command(update=updates, goto=next_node)

    def music_remake(self, state: UnifiedState):
        """Mevcut müziği yeniden üretir"""
        
        print("\n🔄 MUSIC REMAKE başladı...")
        
        # Remake için Suno API'yi kullan
        system_message = """Mevcut müziği kullanıcının geri bildirimine göre yeniden düzenle.
Orijinal tarzı koru ama istenen değişiklikleri uygula."""

        human_message = """
Orijinal stil: {original_style}
Orijinal başlık: {original_title}
Kullanıcı geri bildirimi: {feedback}

Yeni müzik parametrelerini oluştur.
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

        # Suno API ile remake
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
                    "messages": ["System: 🔄 Müzik yeniden üretildi"]
                },
                goto="music_selection_prompt"
            )
        else:
            return Command(
                update={
                    "error_message": "Remake başarısız",
                    "messages": ["System: ❌ Müzik yeniden üretilemedi"]
                },
                goto="communication_agent"
            )

    # ================================================================
    # COVER GENERATION LAYER  
    # ================================================================

    def cover_generator(self, state: UnifiedState):
        """Albüm kapağı üretir"""
        
        print("\n🖼️ COVER GENERATOR başladı...")
        
        system_message = """Sen müzik kapağı yaratma uzmanısın.
        
# KURALLAR:
- Minimalist ve etkileyici tasarımlar
- Müziğin ruhunu yansıtan görseller
- Fazla detay ve karmaşıklıktan kaçın
- Prompt İNGİLİZCE olmalı
- Kapağa yazı ekleme (istenmedikçe)
"""

        human_message = """
Müzik stili: {music_style}
Müzik başlığı: {music_title}
Ek açıklama: {cover_description}

Bu müzik için etkileyici bir kapak tasarımı prompt'u oluştur.
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

        # Google API ile görsel üret
        import uuid
        cover_id = str(uuid.uuid4())
        image_path = f"artifacts/generated_images/{cover_id}.png"
        
        try:
            generated_path = self.google_api.generate_image(result.prompt, image_path)
            
            # Görev kuyruğunu güncelle
            remaining_tasks = [t for t in state.get("task_queue", []) if t != "cover"]
            completed = state.get("completed_tasks", []) + ["cover"]
            
            print(f"   ✅ Kapak üretildi: {generated_path}")
            
            # Video görevi var mı?
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
                    "messages": ["System: 🖼️ Kapak üretildi"]
                },
                goto=next_node
            )
        except Exception as e:
            print(f"   ❌ Kapak üretilemedi: {e}")
            return Command(
                update={
                    "error_message": str(e),
                    "last_error_stage": "cover_generator",
                    "messages": [f"System: ❌ Kapak üretiminde hata: {e}"]
                },
                goto="communication_agent"
            )

    # ================================================================
    # VIDEO GENERATION LAYER
    # ================================================================

    def video_generator(self, state: UnifiedState):
        """Müzik + Kapak = Video"""
        
        print("\n🎬 VIDEO GENERATOR başladı...")
        
        import subprocess
        import uuid
        
        image_path = state.get("cover_image_path")
        audio_path = state.get("selected_audio_file_path")
        
        print(f"   Image: {image_path}")
        print(f"   Audio: {audio_path}")
        
        if not image_path or not audio_path:
            return Command(
                update={
                    "error_message": "Video için eksik dosya",
                    "messages": ["System: ❌ Video için müzik veya kapak eksik"]
                },
                goto="communication_agent"
            )
        
        try:
            os.makedirs("artifacts/final_videos", exist_ok=True)
            output_name = f"{uuid.uuid4()}.mp4"
            output_path = f"artifacts/final_videos/{output_name}"
            
            # FFmpeg komutu
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
            
            print("   🎬 FFmpeg çalıştırılıyor...")
            subprocess.run(command, check=True, capture_output=True, text=True)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                # Görev kuyruğunu güncelle
                remaining_tasks = [t for t in state.get("task_queue", []) if t != "video"]
                completed = state.get("completed_tasks", []) + ["video"]
                
                print(f"   ✅ Video oluşturuldu: {output_path}")
                
                return Command(
                    update={
                        "video_file_path": output_path,
                        "is_video_generated": True,
                        "current_stage": "delivering",
                        "task_queue": remaining_tasks,
                        "completed_tasks": completed,
                        "messages": ["System: 🎬 Video oluşturuldu"]
                    },
                    goto="delivery_agent"
                )
            else:
                raise Exception("Video dosyası oluşturulamadı")
                
        except Exception as e:
            print(f"   ❌ Video hatası: {e}")
            return Command(
                update={
                    "error_message": str(e),
                    "last_error_stage": "video_generator",
                    "messages": [f"System: ❌ Video oluşturulamadı: {e}"]
                },
                goto="communication_agent"
            )

    # ================================================================
    # DELIVERY LAYER
    # ================================================================

    def delivery_agent(self, state: UnifiedState):
        """Üretilen içerikleri kullanıcıya link olarak teslim eder"""
        
        print("\n📦 DELIVERY AGENT başladı...")
        
        phone = state["phone_number"]
        delivered = []
        
        # Müzik teslimi (link olarak)
        if state.get("is_music_selected") and state.get("selected_audio_file_path"):
            audio_path = state["selected_audio_file_path"]
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(audio_path)
                else:
                    filename = os.path.basename(audio_path)
                    file_url = f"http://localhost:5000/files/music/{filename}"
                
                self.message_helper.send_message(phone, f"🎵 Seçtiğin müzik:\n{file_url}")
                delivered.append("music")
                print(f"   ✅ Müzik linki teslim edildi: {file_url}")
                time.sleep(2)
            except Exception as e:
                print(f"   ❌ Müzik teslim hatası: {e}")
        
        # Kapak teslimi (link olarak)
        if state.get("is_cover_generated") and state.get("cover_image_path"):
            cover_path = state["cover_image_path"]
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(cover_path)
                else:
                    filename = os.path.basename(cover_path)
                    file_url = f"http://localhost:5000/files/image/{filename}"
                
                self.message_helper.send_message(phone, f"🖼️ Albüm kapağı:\n{file_url}")
                delivered.append("cover")
                print(f"   ✅ Kapak linki teslim edildi: {file_url}")
                time.sleep(2)
            except Exception as e:
                print(f"   ❌ Kapak teslim hatası: {e}")
        
        # Video teslimi (link olarak)
        if state.get("is_video_generated") and state.get("video_file_path"):
            video_path = state["video_file_path"]
            try:
                if hasattr(self, 'get_file_url') and self.get_file_url:
                    file_url = self.get_file_url(video_path)
                else:
                    filename = os.path.basename(video_path)
                    file_url = f"http://localhost:5000/files/video/{filename}"
                
                self.message_helper.send_message(phone, f"🎬 Müzik videon:\n{file_url}")
                delivered.append("video")
                print(f"   ✅ Video linki teslim edildi: {file_url}")
                time.sleep(2)
            except Exception as e:
                print(f"   ❌ Video teslim hatası: {e}")
        
        # Kapanış mesajı
        if delivered:
            closing_message = "✨ Tüm içerikler hazır! Başka bir şey ister misin?"
        else:
            closing_message = "Hmm, gönderecek içerik bulamadım. Ne yapmamı istersin?"
        
        self.message_helper.send_message(phone, closing_message)
        
        return Command(
            update={
                "current_stage": "completed",
                "messages": [
                    f"System: Teslim edildi: {delivered}",
                    f"Assistant: {closing_message}"
                ]
            },
            goto="wait_user"
        )

    def finish(self, state: UnifiedState):
        """Workflow'u sonlandırır"""
        print("\n✅ WORKFLOW TAMAMLANDI")
        return state

    # ================================================================
    # MEDIA SENDERS (Direct)
    # ================================================================

    def send_music(self, state: UnifiedState):
        """Seçili müziği gönderir"""
        phone = state["phone_number"]
        audio_path = state.get("selected_audio_file_path")
        
        if not audio_path:
            return Command(
                update={"messages": ["System: Gönderilecek müzik yok"]},
                goto="communication_agent"
            )
        
        try:
            self.message_helper.send_audio(phone, audio_path)
            return Command(
                update={"messages": ["System: 🎵 Müzik gönderildi"]},
                goto="communication_agent"
            )
        except Exception as e:
            return Command(
                update={"messages": [f"System: Müzik gönderilemedi: {e}"]},
                goto="communication_agent"
            )

    def send_cover(self, state: UnifiedState):
        """Kapak görselini gönderir"""
        phone = state["phone_number"]
        cover_path = state.get("cover_image_path")
        
        if not cover_path:
            return Command(
                update={"messages": ["System: Gönderilecek kapak yok"]},
                goto="communication_agent"
            )
        
        try:
            self.message_helper.send_message(phone, "🖼️ Kapak görseli:")
            # send_image metodu eklenecek
            return Command(
                update={"messages": ["System: 🖼️ Kapak gönderildi"]},
                goto="communication_agent"
            )
        except Exception as e:
            return Command(
                update={"messages": [f"System: Kapak gönderilemedi: {e}"]},
                goto="communication_agent"
            )

    def send_video(self, state: UnifiedState):
        """Videoyu gönderir"""
        phone = state["phone_number"]
        video_path = state.get("video_file_path")
        
        if not video_path:
            return Command(
                update={"messages": ["System: Gönderilecek video yok"]},
                goto="communication_agent"
            )
        
        try:
            self.message_helper.send_video(phone, video_path)
            return Command(
                update={"messages": ["System: 🎬 Video gönderildi"]},
                goto="communication_agent"
            )
        except Exception as e:
            return Command(
                update={"messages": [f"System: Video gönderilemedi: {e}"]},
                goto="communication_agent"
            )

    # ================================================================
    # GRAPH SETUP
    # ================================================================

    def build_graph(self):
        """LangGraph workflow'unu oluşturur"""
        
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