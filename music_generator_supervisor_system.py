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

# İstek music supervisora gelir -> 
# Supervisor music mi üretecek, olan müziğe tekrar bir revize mi yapacak yoksa mevcut müziğin personasını mı kaydedecek bir karar verir.
# Görev tamamlanıp system supervisor'a gönderir.



load_dotenv()


class MusicSupervizorAgentSystem:

    def __init__(self):
        self.llm= ChatOpenAI(model = "gpt-5")
        self.suno_api = SunoAPI()
    

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


        supervisor_chain = supervisor_template | self.llm.with_structured_output(MusicGenerationAgentBaseModel)

        # System Supervisor Yapısından gelen istek ve seçilmiş bir şarkı olup olmadığı bilgisi buraya gönderilir.
        response = supervisor_chain.invoke({
            "request": state["request"],
            "is_generated": True if state.get("selected_audio_url",None) else False
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
            print(request_detail)
            return {
                "request_details_from_supervisor":request_detail
            }


        print(f"--- Musif Generation Workflow Transition: Router -> {goto.upper()} ---")

        return Command(
            update = {
                "step_list": [goto],
                "request_details_from_supervisor" : [request_detail]
            },
            goto=goto
        )


    def generate_music(self, state: MusicGenerationState):
        """Yeni müzik üretir. Supervisor'dan gelen talimatları LLM ile işler."""
        
        system_message = """Sen profesyonel bir müzik yaratma uzmanısın. Sana verilen yönergelere uyarak detaylı bir müzik üretme şablonu üret. Senden istediğim çıktıların özellikleri şu şekilde:
        ##EĞER SÖZLÜ ŞARKI YAZACAKSAN PROMPT İÇİNDE SADECE ŞARKI SÖZLERİ OLSUN.
        ## DİĞER BÜTÜN YÖNERGELERİ İNGİLİZCE YAZ. SADECE ŞARKIYI YAZACAĞIN SÖZLER PROMPT İÇİNDE O DİLDE OLSUN.
        ## negative_tags kullanmaktan çekinme. Bağlama uygun olmayan yapıları kaldırabilirsin.
        
        - custom_mode : Gelişmiş ses oluşturma ayarları için Özel Modu etkinleştirir.
            * Özel modu kullanmak için *True* olarak ayarla(style ve title gereklidir; instrumental = True ise, prompt sadece şarkı sözü olarak kullanılır.)
            * Özel mod istenmiyorsa False olarak ayarla (yalnızca prompt gereklidir, şarkı sözleri: prompt'a göre otomatik ayarlanacaktır.)
        
        - instrumental : Sesin enstrümantal (sözsüz) olup olmadığını belirler.
            * Özel modda(custom_mode = True) Sadece stil ve başlık yeterlidir, prompt'a gerek yoktur. 
            * (custom_mode= False) Gerekli alanlar üzerinde etkisi yoktur (sadece prompt) instrumental = False ise, özel olmayan modda şarkı sözleri otomatik oluşturulur.

        
        - prompt : İstenen ses içeriğinin açıklaması
            * Özel Modda (custom_mode =True) instrumental = False ilse gereklidir. Prompt, şarkının sözü olarak kullanılacaktır. Yani şarkının sözleri promptdaki içerikten oluşturulacaktır.
            * **Maksimum 3000 karakter olmalıdır.**
            * Özel Olmayan Modda (custom_mode =False) Her zaman gereklidir. PRompt, temel fikir olarak hizmet eder ve şarkı sözleri buna göre otomatik olarak oluşturulur (prompt içeriği ile birebir eşleşmez.) Maksimum 500 karakterdir.

            # Şarkı sözleri yazarken bir profesyonel gibi düşün. İnsanları etkileyecek, müziği dinlettirecek şekilde kafiyelere, sözlerin vuruculuğuna dikkat et.
            

        - style : Ses için müzik stili veya türü
            * Özel Modda(custom_mode=True) gereklidir. Örnekler: "Jazz", "Classical", "Electronic."
            * Özel Olmayan Modda (custom_mode=False) boş bırakılır.
            **Maksimum boyut: 200 karakter**
        
        - title: Üretilen müzik parçasının başlığı
            * Özel Modda(custom_mode=True) gereklidir. Maksimum uzunluğu 80 karakterdir (Örnek: Peaceful Piano Meditation)
            * Özel Olmayan Modda(custom_mode = False) boş bırak.

        - negative_tags: Oluşturulan sesten çıkarılacak müzik tarzları veya özellikleri
            * İsteğe bağlıdır. Belirli tarzları önlemek için kullan. Eğer bir şey koymak istemiyorsan boş string değer olabilir.
            Örnek: "Heavy Metal, Upbeat Drums"
        
        - vocal_gender: Üretilen vocalde tercih edilen vocal cinsiyeti. (m: male, f: female) (sadece f ya da m olabilir.)

        - style_weight: Sağlanan stil kılavuzunun ağırlığı (Aralık 0 ile 1 arası)

        - weirdness_constraint: Yaratıcı sapma/yenilik üzerindeki kısıtlama (Aralık 0 ile 1 arası)

        - audio_weight: Giriş sesinin ağırlığı (uygulanabilir olduğunda) (Aralık 0 ile 1 arası)

        
        Senden sana verilen göreve uygun detaylı ve eksiksiz bir müzik üretme klavuzu üretmen bekleniyor. Yönergeleri uygula ve karakter kısıtlarına dikkat et.
        """
        
        human_message = """Talimat: {request_detail}
        
        
        Bu talimata göre müzik üretim parametrelerini oluştur."""
        
        generate_music_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])
        
        generate_music_chain = generate_music_template | self.llm.with_structured_output(MusicBaseModel)
        
        result = generate_music_chain.invoke({
            "request_detail": state["request_details_from_supervisor"][-1],  # Son talimat
        })
        



        #SunoAPI'yi çağır
        api_result = self.suno_api.create_music(state, music_params=result)
        
        #Node kendi state güncellemesini döndürmeli
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
                "error_message": api_result.get("error", "Bilinmeyen hata")
            }






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

        state = self.suno_api.create_and_save_persona(state=state)

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

        remake_music_chain = remake_music_template | self.llm.with_structured_output(MusicBaseModel)

        result = remake_music_chain.invoke({
            "request": state["request_details_from_supervisor"]
        })




    def set_graph(self):
        """LangGraph yapısını kurar."""
        
        graph = StateGraph(MusicGenerationState)
        
        # Node'ları ekle
        graph.add_node("supervisor", self.supervisor_agent)
        graph.add_node("generate_music", self.generate_music)
        graph.add_node("persona_saver", self.persona_saver)
        graph.add_node("remake_music", self.remake_music)
        
        # Başlangıç noktası
        graph.set_entry_point("supervisor")
        
        # Supervisor'dan Command ile gidiliyor (goto otomatik yönlendirme)
        # Diğer node'lar işlerini bitirince END'e gitsin
        graph.add_edge("generate_music", END)
        graph.add_edge("persona_saver", END)
        graph.add_edge("remake_music", END)
        
        # Compile et
        self.workflow = graph.compile()
        
        return self.workflow


        
agent = MusicSupervizorAgentSystem()

flow = agent.set_graph()

result = flow.invoke({
    "request": "Bana ortaçağ türk şarkılarıyla (kopuz, gırtlak müziği vb) eski anadolu celtic ezgileri birleştiren, detaylı ve güzel bir instrümental müzik yapar mısın"
})


