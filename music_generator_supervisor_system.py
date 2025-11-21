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


        
class RemakeMusicBaseModel(BaseModel):
    prompt: str = Field(...,description = "Yeniden üretilecek müziğin detaylı açıklaması")
    style: str = Field(...,description = "Yeniden üretilecek müziğin stili")
    title: str = Field(...,description = "Yeniden üretilecek müziğin başlığı")
    instrumental: bool = Field(...,description = "Yeniden üretilecek müziğin türü")
    negative_tags: str = Field(..., description = "Yeniden üretilecek müzikten hariç tutulacak müzik stilleri veya özellikleri")
    vocal_gender: Literal["f","m"] = Field(...,description = "Yeniden üretilecek müziği söyleyenin cinsiyeti")
    style_weight: float = Field(ge=0,le=1,description = "Sağlanan stil rehberliğinin ağırlığı")
    weirdness_constraint: float = Field(ge=0,le=1,description ="Yaratıcı sapma/yeni olma üzerindeki kısıtlama" )
    audio_weight: float = Field(ge=0,le=1,description ="giriş audio'sunun etkisinin ağırlığı(uygulanabilir olduğunda)")

class MusicGenerationAgentBaseModel(BaseModel):

    next: Literal["generate_music", "persona_saver", "remake_music","return"] = Field(...,description = "Sonraki adımın ne olduğu bilgisi.")
    # Düşünme bu şekilde ileri doğru sürekli devam eder.
    reason: str = Field(..., "Bu kararı neden aldığının gerekçesi")
    request_detail: str = Field("Gelen isteğin sıradaki yapıya verilecek detaylı açıklaması")


class MusicSupervizorAgentSystem:

    def __init__(self):
        self.llm= ChatOpenAI(model = "gpt-5")
        self.suna_api = SunoAPI()
    

    def supervisor_agent(self,state: MusicGenerationState):
        system_message = """Sen bir müzik üretim uzmanısın. Gelen isteğe göre hangi aracı kullanacağını seçeceksin.

        generate_music: Eğer müzik üretmekle alakalı bir istek geldiyse, **generate_music**
        persona_saver: Eğer kullanıcı yapmış olduğun şarkının personasını beğendiyse, bu yapı mevcut üretilen şarkının personasını kaydeder. Eğer buna uygun bir istem gelirse bu endpoint'i kullan.
        remake_music: Eğer kullanıcı üretilen müziği beğenmediyse ya da yeniden üretilmesini söylerse, sözleri beğenmediyse **remake_music** yapısına yönlendirilir. Burada parça yeniden yapılır.
        return: Eğer yapılacak bir görev yoksa, görev tanımı yanlışsa ya da eksik bir context varsa ya da seçilen bir şarkı yoksa ve seçilen şarkı olmamasına rağmen persona üretilmek isteniyorsa **return**'a yönlendir. 
        
        Bu kararları aldıktan sonra neden bu kararı aldığının açıklamasını **reason** kısmına yazmanı istiyorum.
        
        Seçilmiş bir şarkı bilgisi var mı yok mu onu sana vereceğim. Eğer seçilmiş bir şarkı yoksa ve ilk defa çalışacaksan remake_music ve persona_saver adreslerine yönlendiremezsin. 

        Seçilmiş Şarkı: True or False
        
        ### reason'u şu şekilde doldur:
        - Eğer generate_music'e gideceksen üretilecek müziğin açıklaması
        - Eğer remake_music'e gideceksen müziğin ne doğrultuda değişeceğinin detaylı bilgisi.


        

        """
    
        human_message = """İstek : {request}.
        
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

        # System Supervisor Yapısından gelen istek ve seçilmiş bir şarkı olup olmadığı bilgisi buraya gönderilir.
        response = supervisor_chain.invoke({
            "request": state["request"],
            "is_generated": True if self["selected_audio_url"] else False
        })


        # Sonraki adım belirlenir. Sonraki adım modelin nereye yönlendireceği bilgisini verir.
        goto = response.next

        # Sonraki adımdaki yapıya ne yapacağını bu çıktı söyler.
        request_detail = response.request_detail



        # Burayı doldur. Burası SystemState'ye yönlendirecek.
        if goto == "persona_saver":
            if len(state["generated_audio_urls"]) == 0:
                print("Henüz Üretilmiş Bir Şarkı Yok")
                # request_step_list'e bu step'i ekle.
                return None



        if goto == "return":
            print("MusicSupervizor Yapısı alacak bir karar bulamadı. Geri dönüyor.")
            return None


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

        system_message = """Sen müziğin personasını kaydetme uzmanısın. Kullanıcı seni kullanıyorsa, daha önce üretilen şarkıyı beğenmiştir. Sana verilen bilgilerden;
        persona_name: Oluşturulacak personanın ismi (Kısa persona içeriği ÖR: Electronic Pop Singer)
        description: Oluşturulacak personanın açıklaması(Persona için önemli, bu yönergelere bakarak da değişebilir ÖR: A modern electronic music style pop singer, skilled in dynamic rhythms and synthesizer tones) 
        """
        
        human_message = """
        Kaydetmeni istediğim personanın ürettiği parçanın özellikleri:

        müziğin üretildiği prompt: {prompt}
        
        müziğin üretildiği style: {style}
        
        müziğin üretildiği title: {title}

        instrumental : {instrumental} (True ise parçada ses yok, False ise parça sözlü)

        Müzikte istenmeyen özellkler: {negative_tags}
        
        Personanın cinsiyeti: {vocal_gender}

        Girilen style'nin parçaya ağırlığı: {style_weight}
        
        Bu verilen bilgilere göre name, description oluştur.
        """


        persona_saver_template = ChatPromptTemplate.from_messages(
            [
                ("system",system_message),
                ("human",human_message)
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
                "negative_tags":state["negative_tags"],
                "style_weight": state["style_weight"]
            }
        )

        state["persona_saver_name"] = result.name
        state["persona_saver_description"] = result.description

        state = self.suna_api.create_and_save_persona(state=state)

        if state["is_persona_saved"]:
            print("--- Persona Başarılı Bir Şekilde Oluşturuldu ve Kaydedildi ---")
        
        else:
            print("--- Persona Oluşturulma ve Kaydedilme İşleminde Hata !!! ---")

        return {
            "persona_saver_name": state["persona_saver_name"],
            "persona_saver_description": state["persona_saver_description"],
            "created_persona_id": state["created_persona_id"]
        }
    
                  


    def remake_music(self,state:MusicGenerationState):
        """Bir ses parçasının çekirdek melodisini koruyarak parçayı yeni bir stile dönüştürür."""


        system_message ="""Sen bir müzik yeniden yaratım uzmanısın. Gelen isteme göre müzik yeniden yaratmasını genişlet.
        Senin görevin bir ses parçasının çekirdek melodisini koruyarak parçayı yeni bir stile dönüştürmek.
        Müziğin personasının değiştirilmesi istenebilir, eğer böyle bir şey isteniyorsa sana verilen şablonda gerekli alanı ona göre doldur.

        prompt: Değiştireceğin müziğin detaylı bir yönergesi, burada neyin değişeceğini değil, ne istediğini yaz.
        style: Yeni müziğin stilini buraya gir (Ör: Classical)
        title: Yeni Müziğin Başlığı (Ör: Peaceful Piano Meditation)
        instrumental: Yeni müzik sözsüz olacaksa True, söze sahip olacaksa False
        negative_tags: Şarkıda olmasını istemediğin bileşenleri gir (Ör: Heavy Metal, Upbeat Drums)
        vocal_gender: Yeni parçayı söyleyenin cinsiyeti (f: female, m: male SADECE f YA DA m)
        style_weight: Sağlanan stil rehberliğinin ağırlığı (0 ile 1 arasında)
        weirdness_constraint: Yaratıcı sapma/yeni olma üzerindeki kısıtlama (0 ile 1 arasında)
        audio_weight: giriş audio'sunun etkisinin ağırlığı(uygulanabilir olduğunda)(0 ile 1 arasında)
        
        """

        human_message = """Senden şu isteme göre bir değişiklik yapman isteniyor:
        İstem: {request}
        """


        remake_music_template = ChatPromptTemplate.from_messages(
            [
                ("system",system_message),
                ("human",human_message)
            ]
        )

        remake_music_chain = remake_music_template | self.llm.with_structured_output(RemakeMusicBaseModel)

        result = remake_music_chain.invoke({
            "request": state["request_details_from_supervisor"]
        })





        









class SunoAPI:

    def __init__(self):
        self.suno_api_key = os.getenv("SUNO_AI_API_KEY")
        self.base_url = "https://api.sunoapi.org/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Klasör
        os.makedirs("artifacts/musics", exist_ok=True)
    
    def create_music(self, state: MusicGenerationState):
            generate_url =f"{self.base_url}/generate"
            payload = None

            # Eğer kullanıcı bir persona seçtiyse müziği o persona oluştursun:
            if state["selected_persona_id"]:
                payload = {
                        "prompt": state["prompt"],
                        "style": state["style"],
                        "title": state["title"],
                        "customMode": state["custom_mode"],
                        "personaId": state.get("persona_id"),
                        "instrumental": state["instrumental"],
                        "model": "V4",
                        "negativeTags": state["negative_tags"],
                        "vocalGender": state["vocal_gender"],
                        "styleWeight": state["style_weight"],
                        "weirdnessConstraint": state["weirdness_constraint"],
                        "audioWeight": state["audio_weight"],
                        "callBackUrl": "https://example.com/callback"
                    }
            else: 
                payload = {
                        "prompt": state["prompt"],
                        "style": state["style"],
                        "title": state["title"],
                        "customMode": state["custom_mode"],
                        "personaId": state["persona_id"],
                        "instrumental": state["instrumental"],
                        "model": state["music_generation_model"],
                        "negativeTags": state["negative_tags"],
                        "vocalGender": state["vocal_gender"],
                        "styleWeight": state["style_weight"],
                        "weirdnessConstraint": state["weirdness_constraint"],
                        "audioWeight": state["audio_weight"],
                        "callBackUrl": "https://example.com/callback"
                    }
                
            print("--- Müzik Üretmek İçin API'ye istek gönderiliyor ---")
            response = requests.post(generate_url, json = payload, headers= self.headers)
            
            # Gelen response'yi al :
            generation_data = response.json()
            print(f" - Müzik Üretimi API Yanıtı: {generation_data.get('code')} -")


            # Burayı doldur. Düzgün bir şey dönsün. REQUEST BODY OLUŞTUR.
            if generation_data.get("code") != 200:
                print("--- Müzik Üretimi Başarısız ---")

                return {"is_generated":False,"current_state":state}
            

            generation_task_id = generation_data["data"]["task_id"]

            # Üretilen müziğin task id'sini alıp indirip bilgileri alalım:
            generated_musics_data = self.wait_and_download(generation_task_id, timeout=state["music_generation_duration_time"])

            # Müzik Üretimini Kontrol Et.
            if not generated_musics_data["is_generate"]:
                print("--- MÜZİK ÜRETİMİ BAŞARISIZ ---")

                return {"is_generated":False,"current_state":state}
            
            state[""]

            audio_ids = [music_data["audio_id"] for music_data in generated_musics_data]

            audio_file_adress = [music_data["audio_id"] for music_data in generated_musics_data]

            audio_url = [music_data["downloaded_file_path"] for music_data in generated_musics_data]
            
            state["generated_audio_ids"] = audio_ids
            state["generated_audio_file_adress"] = audio_file_adress
            state["generated_audio_urls"] = audio_url

            return {"is_generated": True,"current_state":state}
    
    





    def create_and_save_persona(self,state: MusicGenerationState):
        print("--- Persona Oluşturuluyor ---")
        create_persona_url = f"{self.base_url}/generate/generate-persona"
        
        payload = {
            "taskId": state.get("persona_saver_task_id"), 
            "audioId": state["persona_saver_audio_id"],
            "name": state["persona_saver_name"],
            "description": state["persona_saver_description"]
        }

        try:
            response = requests.post(create_persona_url, json = payload, headers=self.headers)

            data = response.json()


            # Eğer Persona üretildiyse ve kaydedildiyse state'ye ekle ve dön.
            if data.get("code") == 200:
                persona_data = data["data"]
                state["created_persona_id"] = data["data"]["personaId"]
                PersonaDB.save_persona(persona_data)

                state["is_persona_saved"] = True
                return state
        
        except Exception as e:
            state["is_persona_saved"] = False
            return state
        
    
            
        
        



    def wait_and_download(self,task_id,timeout,download=True):
        """Gelen müzik üretimi, müzik remake gibi görevlerde task_id işlemlerini yürütür"""
        record_info_url = f"{self.base_url}/generate/record-info"
        print(f"-- Müzik Üretimi İçin {timeout} Saniye Bekleniyor --")

        time.sleep(timeout)

        response = requests.get(
                    f"{record_info_url}?taskId={task_id}", 
                    headers=self.headers
                )
        data = response.json()


        if "data" not in data:
            print(" ---- Task ID İçerisinde Veri Yok.")
            return {"is_generate":False, "reason":"empty_data"}
        
        status = data["data"].get("status")
        print(f"-- Müzik Üretim API'sinin status çıktısı: {status} --")

        if status  not in ["SUCCESS", "TEXT_SUCCESS"]:
            return {"is_generate":False, "reason": "status_failed"}
        
        suno_data = data["data"]["response"].get("sunoData", [])

        if not suno_data:
            print("--- Status success ama müzik verisi yok ---")
            return {"is_generate":False, "reason": "status_failed"}
        
        audio_details = []

        for audio_feature in suno_data:
            detail = {}
            # 2 müzik için de detayları kaydet (müzik id ve audio url'si):
            detail["audio_id"] = audio_feature["id"]
            detail["audio_url"] = audio_feature["audio_url"]

            # Eğer üretilen müzik indirilmek isteniyorsa indirilip url'leri döner.
            if download:
                file_name = f"{detail["audio_id"]}.mp3"
                file_path = f"artifacts/musics/{file_name}"
                audio_res = requests.get(detail["audio_url"])
                with open(file_path, "wb") as f:
                    f.write(audio_res.content)
            
                detail["downloaded"] =True
                detail["downloaded_file_path"] = file_path

            audio_details.append(detail)
           

        return {"is_generate":True,data: audio_details}
    









class PersonaChangerBaseModel(BaseModel):
    name: Optional[str] = Field(...,description = "Personanın kişiliğini yansıtan ismi (Örnek: Electronic Pop Singer)")
    description: Optional[str] = Field(...,description = "Personanın kişilik açıklaması ")
    



