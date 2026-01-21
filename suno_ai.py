"""
Suno AI API Wrapper
===================
Müzik üretimi, remake ve persona yönetimi için Suno API entegrasyonu.
"""

import os
import time
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from personadb_utils import PersonaDB
from base_models import MusicBaseModel

load_dotenv()


class SunoAPI:
    """Suno AI API wrapper"""

    def __init__(self):
        self.suno_api_key = os.getenv("SUNO_AI_API_KEY")
        self.base_url = "https://api.sunoapi.org/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.suno_api_key}",
            "Content-Type": "application/json"
        }
        
        # Klasörleri oluştur
        os.makedirs("artifacts/musics", exist_ok=True)

    def create_music(self, state: Dict[str, Any], music_params: MusicBaseModel) -> Dict[str, Any]:
        """
        Yeni müzik üretir.
        
        Args:
            state: Mevcut workflow state'i
            music_params: Müzik üretim parametreleri
            
        Returns:
            {"is_generated": bool, "current_state": state, "error": str (optional)}
        """
        
        generate_url = f"{self.base_url}/generate"
        
        payload = {
            "prompt": music_params.prompt,
            "style": music_params.style,
            "title": music_params.title,
            "instrumental": music_params.instrumental,
            "negativeTags": music_params.negative_tags,
            "vocalGender": music_params.vocal_gender,
            "styleWeight": music_params.style_weight,
            "weirdnessConstraint": music_params.weirdness_constraint,
            "audioWeight": music_params.audio_weight,
            "customMode": True,
            "model": state.get("music_generation_model", "V4"),
            "callBackUrl": "https://example.com/callback"
        }

        # Persona seçildiyse ekle
        if state.get("selected_persona_id"):
            payload["personaId"] = state["selected_persona_id"]

        print("📡 Suno API'ye istek gönderiliyor...")
        
        try:
            response = requests.post(generate_url, json=payload, headers=self.headers)
            generation_data = response.json()
            
            print(f"   API Yanıt Kodu: {generation_data.get('code')}")

            if generation_data.get("code") != 200:
                print(f"   ❌ API Hatası: {generation_data}")
                return {
                    "is_generated": False, 
                    "current_state": state,
                    "error": f"API error: {generation_data.get('message', 'Unknown')}"
                }

            time.sleep(1)
            
            task_id = generation_data["data"]["taskId"]
            print(f"   Task ID: {task_id}")

            # Müziği bekle ve indir
            result = self.wait_and_download(task_id)

            if not result["is_generate"]:
                print(f"   ❌ Üretim başarısız: {result.get('reason')}")
                return {
                    "is_generated": False, 
                    "current_state": state,
                    "error": result.get("reason", "Generation failed")
                }

            # State'i güncelle
            audio_data = result["data"]
            
            state["generated_audio_ids"] = [d["audio_id"] for d in audio_data]
            state["generated_audio_urls"] = [d["audio_url"] for d in audio_data]
            state["generated_audio_file_adress"] = [d["downloaded_file_path"] for d in audio_data]
            
            print(f"   ✅ {len(audio_data)} müzik üretildi!")

            return {"is_generated": True, "current_state": state}
            
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return {
                "is_generated": False, 
                "current_state": state,
                "error": str(e)
            }

    def remake_music(self, state: Dict[str, Any], remake_params: MusicBaseModel) -> Dict[str, Any]:
        """
        Mevcut müziği yeniden üretir (cover/remix).
        
        Args:
            state: Mevcut workflow state'i (selected_audio_url gerekli)
            remake_params: Yeniden üretim parametreleri
            
        Returns:
            {"is_generated": bool, "current_state": state, "error": str (optional)}
        """
        
        print("🔄 Müzik Remake başlıyor...")
        
        remake_url = f"{self.base_url}/generate/upload-cover"
        
        source_url = state.get("selected_audio_url")
        if not source_url:
            # Üretilen müziklerden birini kullan
            urls = state.get("generated_audio_urls", [])
            if urls:
                source_url = urls[0]
            else:
                return {
                    "is_generated": False,
                    "current_state": state,
                    "error": "No source audio for remake"
                }
        
        payload = {
            "uploadUrl": source_url,
            "prompt": remake_params.prompt,
            "style": remake_params.style,
            "title": remake_params.title,
            "instrumental": remake_params.instrumental,
            "negativeTags": remake_params.negative_tags,
            "vocalGender": remake_params.vocal_gender,
            "styleWeight": remake_params.style_weight,
            "weirdnessConstraint": remake_params.weirdness_constraint,
            "audioWeight": remake_params.audio_weight,
            "customMode": True,
            "model": state.get("music_generation_model", "V4"),
            "callBackUrl": "https://example.com/callback"
        }

        if state.get("selected_persona_id"):
            payload["personaId"] = state["selected_persona_id"]

        try:
            print("📡 Remake API'ye istek gönderiliyor...")
            response = requests.post(remake_url, json=payload, headers=self.headers)
            data = response.json()
            
            print(f"   API Yanıt Kodu: {data.get('code')}")

            if data.get("code") != 200:
                return {
                    "is_generated": False, 
                    "current_state": state,
                    "error": f"API error: {data.get('message', 'Unknown')}"
                }

            task_id = data["data"]["taskId"]
            print(f"   Task ID: {task_id}")

            # Bekle ve indir
            result = self.wait_and_download(task_id)

            if not result["is_generate"]:
                return {
                    "is_generated": False, 
                    "current_state": state,
                    "error": result.get("reason", "Remake failed")
                }

            # State'i güncelle
            audio_data = result["data"]
            
            state["generated_audio_ids"] = [d["audio_id"] for d in audio_data]
            state["generated_audio_urls"] = [d["audio_url"] for d in audio_data]
            state["generated_audio_file_adress"] = [d["downloaded_file_path"] for d in audio_data]
            
            print(f"   ✅ Remake tamamlandı!")

            return {"is_generated": True, "current_state": state}

        except Exception as e:
            print(f"   ❌ Remake Exception: {e}")
            return {
                "is_generated": False, 
                "current_state": state,
                "error": str(e)
            }

    def create_and_save_persona(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mevcut müzikten persona oluşturur ve kaydeder.
        
        Args:
            state: persona_saver_* alanları dolu olmalı
            
        Returns:
            Güncellenmiş state
        """
        
        print("🎭 Persona oluşturuluyor...")
        
        create_persona_url = f"{self.base_url}/generate/generate-persona"
        
        # Gerekli bilgileri al
        task_id = state.get("persona_saver_task_id")
        audio_id = state.get("persona_saver_audio_id") or state.get("selected_audio_id")
        
        if not audio_id:
            # İlk üretilen müziği kullan
            audio_ids = state.get("generated_audio_ids", [])
            if audio_ids:
                audio_id = audio_ids[0]
        
        payload = {
            "taskId": task_id,
            "audioId": audio_id,
            "name": state.get("persona_saver_name", "Custom Persona"),
            "description": state.get("persona_saver_description", "Auto-generated persona")
        }

        try:
            response = requests.post(create_persona_url, json=payload, headers=self.headers)
            data = response.json()

            if data.get("code") == 200:
                persona_data = data["data"]
                state["created_persona_id"] = persona_data.get("personaId")
                
                # Veritabanına kaydet
                PersonaDB.save_persona(persona_data)
                
                state["is_persona_saved"] = True
                print(f"   ✅ Persona kaydedildi: {state['created_persona_id']}")
            else:
                state["is_persona_saved"] = False
                print(f"   ❌ Persona kaydedilemedi: {data}")

        except Exception as e:
            state["is_persona_saved"] = False
            print(f"   ❌ Persona Exception: {e}")

        return state

    def wait_and_download(self, task_id: str, max_wait: int = 400, poll_interval: int = 20, download: bool = True) -> Dict[str, Any]:
        """
        Task tamamlanana kadar polling yapar ve sonuçları indirir.
        
        Args:
            task_id: Suno task ID
            max_wait: Maksimum bekleme süresi (saniye) - default 400
            poll_interval: Kontrol aralığı (saniye) - default 20
            download: Müzikleri indir mi?
            
        Returns:
            {"is_generate": bool, "data": [...], "reason": str (optional)}
        """
        
        record_info_url = f"{self.base_url}/generate/record-info"
        
        print(f"   ⏳ Polling başlıyor (max {max_wait}s, her {poll_interval}s)")
        
        elapsed = 0
        last_status = None
        
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            
            try:
                response = requests.get(
                    f"{record_info_url}?taskId={task_id}",
                    headers=self.headers
                )
                data = response.json()

                if "data" not in data:
                    print(f"   [{elapsed}s] ⚠️ Veri yok, bekleniyor...")
                    continue

                status = data["data"].get("status")
                
                # Status değiştiyse logla
                if status != last_status:
                    print(f"   [{elapsed}s] Status: {status}")
                    last_status = status

                # Başarılı durumlar - sadece SUCCESS tam bitmiş demek
                if status == "SUCCESS":
                    print(f"   ✅ Üretim tamamlandı! ({elapsed}s)")
                    
                    suno_data = data["data"]["response"].get("sunoData", [])
                    
                    # Debug: response yapısını göster
                    print(f"   📋 Suno data count: {len(suno_data)}")
                    if suno_data:
                        print(f"   📋 First item keys: {list(suno_data[0].keys())}")

                    if not suno_data:
                        print("   ⚠️ Müzik verisi boş")
                        return {"is_generate": False, "reason": "no_audio_data"}

                    audio_details = []

                    for idx, audio_feature in enumerate(suno_data):
                        # audioUrl farklı key'lerde olabilir
                        audio_url = (
                            audio_feature.get("audioUrl") or 
                            audio_feature.get("audio_url") or 
                            audio_feature.get("streamAudioUrl") or
                            audio_feature.get("sourceAudioUrl") or
                            ""
                        )
                        
                        audio_id = (
                            audio_feature.get("id") or 
                            audio_feature.get("audioId") or
                            f"unknown_{idx}"
                        )
                        
                        print(f"   🎵 Item {idx}: id={audio_id}, url={audio_url[:50] if audio_url else 'EMPTY'}...")
                        
                        # audioUrl boşsa bu parça henüz hazır değil
                        if not audio_url:
                            print(f"   ⚠️ Audio URL boş, atlanıyor: {audio_id}")
                            continue
                        
                        detail = {
                            "audio_id": audio_id,
                            "audio_url": audio_url,
                            "downloaded": False,
                            "downloaded_file_path": None
                        }

                        if download and audio_url:
                            try:
                                file_name = f"{audio_id}.mp3"
                                file_path = f"artifacts/musics/{file_name}"
                                
                                audio_response = requests.get(audio_url)
                                if audio_response.status_code == 200:
                                    with open(file_path, "wb") as f:
                                        f.write(audio_response.content)

                                    detail["downloaded"] = True
                                    detail["downloaded_file_path"] = file_path
                                    print(f"   📥 İndirildi: {file_path}")
                                else:
                                    print(f"   ⚠️ İndirme hatası: HTTP {audio_response.status_code}")
                            except Exception as e:
                                print(f"   ⚠️ İndirme hatası: {e}")

                        audio_details.append(detail)

                    # Hiç indirilen müzik yoksa hata
                    if not audio_details:
                        print("   ❌ Hiç müzik indirilemedi")
                        return {"is_generate": False, "reason": "no_downloadable_audio"}

                    return {"is_generate": True, "data": audio_details}
                
                # TEXT_SUCCESS / FIRST_SUCCESS = sözler hazır ama müzik henüz bitmedi, beklemeye devam
                elif status in ["TEXT_SUCCESS", "FIRST_SUCCESS"]:
                    print(f"   [{elapsed}s] ⏳ İlk aşama tamamlandı, müzik üretiliyor...")
                    continue
                
                # Hata durumları
                elif status in ["FAILED", "ERROR", "CANCELLED"]:
                    print(f"   ❌ Üretim başarısız: {status}")
                    return {"is_generate": False, "reason": f"status_{status}"}
                
                # Devam eden durumlar - beklemeye devam
                # PENDING, PROCESSING, FIRST_SUCCESS, GENERATING, vb.
                
            except Exception as e:
                print(f"   [{elapsed}s] ⚠️ Polling hatası: {e}")
                continue
        
        # Timeout
        print(f"   ❌ Timeout! ({max_wait}s)")
        return {"is_generate": False, "reason": "timeout"}