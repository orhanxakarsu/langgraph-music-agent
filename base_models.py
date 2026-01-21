from pydantic import BaseModel, Field
from typing import Optional, Literal, List


class PersonaChangerBaseModel(BaseModel):
    name: Optional[str] = Field(..., description="Personanın kişiliğini yansıtan ismi (Örnek: Electronic Pop Singer)")
    description: Optional[str] = Field(..., description="Personanın kişilik açıklaması")


class MusicBaseModel(BaseModel):
    prompt: str = Field(..., description="Şarkı sözleri veya açıklama")
    style: str = Field(..., description="Müzik stili")
    title: str = Field(..., description="Şarkı başlığı")
    instrumental: bool = Field(..., description="Enstrümantal mı?")
    negative_tags: str = Field(default="", description="İstenmeyen özellikler")
    vocal_gender: Literal["f", "m"] = Field(..., description="Vokal cinsiyeti")
    style_weight: float = Field(default=0.65, ge=0, le=1)
    weirdness_constraint: float = Field(default=0.65, ge=0, le=1)
    audio_weight: float = Field(default=0.65, ge=0, le=1)


class MusicGenerationAgentBaseModel(BaseModel):
    next: Literal["generate_music", "persona_saver", "remake_music", "return"] = Field(
        ..., description="Sonraki adımın ne olduğu bilgisi."
    )
    reason: str = Field(..., description="Bu kararı neden aldığının gerekçesi")
    request_detail: str = Field(..., description="Gelen isteğin sıradaki yapıya verilecek detaylı açıklaması")


class CommunicationDecisionBaseModel(BaseModel):
    """Communication agent'in karar modeli"""
    action: Literal[
        "send_message",
        "send_music",
        "send_cover",
        "send_video",
        "choice_persona",
        "task_planner",  # Yeni: Supervisor'a yönlendir
        "wait_user",
        "finish"
    ] = Field(description="Alınacak aksiyon")
    
    description: str = Field(
        description="Aksiyonun detaylı açıklaması veya kullanıcıya gönderilecek mesaj"
    )


# ============== YENİ MODELLER ==============

class TaskPlannerDecisionBaseModel(BaseModel):
    """Task Planner'ın karar modeli - hangi görevlerin yapılacağını belirler"""
    
    tasks: List[Literal["music", "cover", "video", "persona_save", "remake"]] = Field(
        description="Yapılacak görevler listesi, sıralı"
    )
    
    music_description: Optional[str] = Field(
        default=None,
        description="Müzik üretimi için detaylı açıklama (eğer music görevi varsa)"
    )
    
    cover_description: Optional[str] = Field(
        default=None, 
        description="Kapak üretimi için açıklama (eğer cover görevi varsa)"
    )
    
    remake_instructions: Optional[str] = Field(
        default=None,
        description="Remake için talimatlar (eğer remake görevi varsa)"
    )
    
    response_to_user: str = Field(
        description="Kullanıcıya verilecek yanıt (işlem başlıyor mesajı)"
    )


class MusicSelectionBaseModel(BaseModel):
    """Kullanıcının müzik seçimi"""
    
    selection: Literal["1", "2", "both", "neither", "remake"] = Field(
        description="Kullanıcının seçimi: 1, 2, ikisi de, hiçbiri, veya yeniden üret"
    )
    
    remake_feedback: Optional[str] = Field(
        default=None,
        description="Eğer remake seçildiyse, kullanıcının geri bildirimi"
    )


class DeliveryDecisionBaseModel(BaseModel):
    """Delivery agent'ın karar modeli"""
    
    action: Literal[
        "deliver_music",
        "deliver_cover", 
        "deliver_video",
        "deliver_all",
        "ask_for_more",
        "finish"
    ] = Field(description="Teslim aksiyonu")
    
    message: str = Field(description="Kullanıcıya gönderilecek mesaj")


class ImagePromptBaseModel(BaseModel):
    """Image generator için prompt modeli"""
    
    prompt: str = Field(description="Görsel üretim prompt'u (İngilizce)")
    style_notes: Optional[str] = Field(default=None, description="Stil notları")