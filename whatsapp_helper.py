"""
WhatsApp Helper
===============
Evolution API kullanarak WhatsApp mesajlaşma.
"""

import os
import base64
from typing import Optional, List, Dict

# Evolution API import - farklı versiyonlar için try/except
try:
    from evolutionapi.client import EvolutionClient
    from evolutionapi.models.message import TextMessage, MediaMessage, MediaType
    EVOLUTION_AVAILABLE = True
except ImportError:
    EVOLUTION_AVAILABLE = False
    print("⚠️ evolutionapi paketi bulunamadı")


class WhatsApp:
    """WhatsApp messaging helper - Evolution API wrapper"""
    
    def __init__(self):
        self.base_url = os.getenv("EVOLUTION_API_URL", "http://server:8585")
        self.api_key = os.getenv("EVOLUTION_API_KEY", "")
        self.instance_name = os.getenv("INSTANCE_NAME", "default")
        
        self.client = None
        if EVOLUTION_AVAILABLE and self.api_key:
            try:
                self.client = EvolutionClient(
                    base_url=self.base_url,
                    api_token=self.api_key
                )
                print("✅ Evolution client başlatıldı")
            except Exception as e:
                print(f"⚠️ Evolution client hatası: {e}")
        
        # İzin verilen numaralar (boşsa herkese izin ver)
        allowed = os.getenv("ALLOWED_NUMBERS", "")
        self.allowed_numbers: List[str] = [n.strip() for n in allowed.split(",") if n.strip()]
    
    def is_allowed(self, phone: str) -> bool:
        """Numaraya izin var mı?"""
        if not self.allowed_numbers:
            return True
        clean_phone = phone.replace("+", "").replace(" ", "").replace("@s.whatsapp.net", "")
        return clean_phone in self.allowed_numbers
    
    def _clean_phone(self, phone: str) -> str:
        """Telefon numarasını temizle"""
        return phone.replace("+", "").replace(" ", "").replace("@s.whatsapp.net", "")
    
    def _get_media_type(self, media_type: str) -> str:
        """MediaType enum değerini al - farklı API versiyonları için"""
        if EVOLUTION_AVAILABLE:
            try:
                # Önce enum'dan dene
                if hasattr(MediaType, media_type.upper()):
                    mt = getattr(MediaType, media_type.upper())
                    return mt.value if hasattr(mt, 'value') else str(mt)
                # Küçük harfle dene
                if hasattr(MediaType, media_type.lower()):
                    mt = getattr(MediaType, media_type.lower())
                    return mt.value if hasattr(mt, 'value') else str(mt)
            except Exception as e:
                print(f"⚠️ MediaType hatası: {e}")
        
        # Fallback: string olarak dön
        return media_type.lower()
    
    def send_message(self, phone: str, text: str) -> dict:
        """Metin mesajı gönder"""
        if not self.client:
            print(f"📱 [MOCK] Mesaj -> {phone}: {text[:50]}...")
            return {"status": "mock"}
        
        try:
            message = TextMessage(
                number=self._clean_phone(phone),
                text=text
            )
            return self.client.messages.send_text(
                self.instance_name,
                message,
                self.api_key
            )
        except Exception as e:
            print(f"❌ Mesaj gönderme hatası: {e}")
            raise
    
    def send_audio(self, phone: str, audio_path: str) -> dict:
        """Ses dosyası gönder"""
        if not self.client:
            print(f"📱 [MOCK] Audio -> {phone}: {audio_path}")
            return {"status": "mock"}
        
        try:
            with open(audio_path, 'rb') as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            
            message = MediaMessage(
                number=self._clean_phone(phone),
                mediatype=self._get_media_type("audio"),
                mimetype="audio/mpeg",
                media=audio_b64,
                fileName=os.path.basename(audio_path)
            )
            return self.client.messages.send_media(
                self.instance_name,
                message,
                self.api_key
            )
        except Exception as e:
            print(f"❌ Audio gönderme hatası: {e}")
            raise
    
    def send_image(self, phone: str, image_path: str, caption: str = None) -> dict:
        """Görsel gönder"""
        if not self.client:
            print(f"📱 [MOCK] Image -> {phone}: {image_path}")
            return {"status": "mock"}
        
        try:
            with open(image_path, 'rb') as f:
                image_b64 = base64.b64encode(f.read()).decode()
            
            ext = os.path.splitext(image_path)[1].lower()
            mimetype_map = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mimetype = mimetype_map.get(ext, 'image/png')
            
            message = MediaMessage(
                number=self._clean_phone(phone),
                mediatype=self._get_media_type("image"),
                mimetype=mimetype,
                media=image_b64,
                fileName=os.path.basename(image_path),
                caption=caption or ""
            )
            return self.client.messages.send_media(
                self.instance_name,
                message,
                self.api_key
            )
        except Exception as e:
            print(f"❌ Image gönderme hatası: {e}")
            raise
    
    def send_video(self, phone: str, video_path: str, caption: str = None) -> dict:
        """Video gönder"""
        if not self.client:
            print(f"📱 [MOCK] Video -> {phone}: {video_path}")
            return {"status": "mock"}
        
        try:
            with open(video_path, 'rb') as f:
                video_b64 = base64.b64encode(f.read()).decode()
            
            message = MediaMessage(
                number=self._clean_phone(phone),
                mediatype=self._get_media_type("video"),
                mimetype="video/mp4",
                media=video_b64,
                fileName=os.path.basename(video_path),
                caption=caption or ""
            )
            return self.client.messages.send_media(
                self.instance_name,
                message,
                self.api_key
            )
        except Exception as e:
            print(f"❌ Video gönderme hatası: {e}")
            raise
    
    def send_document(self, phone: str, doc_path: str, filename: str = None) -> dict:
        """Döküman gönder"""
        if not self.client:
            print(f"📱 [MOCK] Document -> {phone}: {doc_path}")
            return {"status": "mock"}
        
        try:
            with open(doc_path, 'rb') as f:
                doc_b64 = base64.b64encode(f.read()).decode()
            
            message = MediaMessage(
                number=self._clean_phone(phone),
                mediatype=self._get_media_type("document"),
                mimetype="application/octet-stream",
                media=doc_b64,
                fileName=filename or os.path.basename(doc_path)
            )
            return self.client.messages.send_media(
                self.instance_name,
                message,
                self.api_key
            )
        except Exception as e:
            print(f"❌ Document gönderme hatası: {e}")
            raise
    
    def parse_webhook(self, webhook_data: dict) -> Optional[Dict]:
        """Webhook verisini parse et"""
        try:
            # Event kontrolü
            if webhook_data.get('event') != 'messages.upsert':
                return None
            
            data = webhook_data.get('data', {})
            key = data.get('key', {})
            
            # Kendi mesajlarımızı ignore et
            if key.get('fromMe', False):
                return None
            
            # Phone numarasını al
            phone = key.get('remoteJid', '').replace('@s.whatsapp.net', '')
            
            if not phone:
                return None
            
            # İzin kontrolü
            if not self.is_allowed(phone):
                print(f"⚠️ {phone} numarasına izin yok")
                return None
            
            # Message ID al (duplicate kontrolü için)
            message_id = key.get('id', '')
            
            message = data.get('message', {})
            
            result = {
                'phone': phone,
                'text': None,
                'type': 'unknown',
                'media_url': None,
                'message_id': message_id  # Duplicate kontrolü için
            }
            
            # Mesaj tipini belirle
            if 'conversation' in message:
                result['type'] = 'text'
                result['text'] = message['conversation']
                
            elif 'extendedTextMessage' in message:
                result['type'] = 'text'
                result['text'] = message['extendedTextMessage'].get('text')
                
            elif 'imageMessage' in message:
                result['type'] = 'image'
                result['text'] = message['imageMessage'].get('caption', '')
                result['media_url'] = message['imageMessage'].get('url')
                
            elif 'audioMessage' in message:
                result['type'] = 'audio'
                result['media_url'] = message['audioMessage'].get('url')
                
            elif 'videoMessage' in message:
                result['type'] = 'video'
                result['text'] = message['videoMessage'].get('caption', '')
                result['media_url'] = message['videoMessage'].get('url')
                
            elif 'documentMessage' in message:
                result['type'] = 'document'
                result['text'] = message['documentMessage'].get('fileName', '')
                result['media_url'] = message['documentMessage'].get('url')
                
            else:
                print(f"⚠️ Desteklenmeyen mesaj tipi: {list(message.keys())}")
                return None
            
            return result
            
        except Exception as e:
            print(f"❌ Webhook parse hatası: {e}")
            import traceback
            traceback.print_exc()
            return None


# Factory function
def create_whatsapp_helper():
    return WhatsApp()