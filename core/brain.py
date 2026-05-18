import os
import re
import threading
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv


class GroqBrain:
    # Iron Dome ile uyumlu kayıtlı protokoller.
    # Bu set dışındaki tool_call'lar yoksayılır ve metin yanıta düşülür.
    VALID_PROTOCOLS = {
        "GOOGLE_SEARCH", "WEB_OPEN", "YT_SEARCH", "YT_PLAY",
        "APP_OPEN", "APP_KILL", "WHATSAPP_MESSAGE", "WHATSAPP_DELETE",
        "VISION", "STRESS_TEST", "TAB_KILL", "SPEAK",
        "FILE_READ", "FILE_SUMMARIZE", "FILE_WRITE",
        "STEAM_LAUNCH", "SYSTEM_POWER",
        "EPIC_LAUNCH", "CLOSE_LAST_TAB",
        "SYSTEM_SHUTDOWN",   # [V9.5] J.A.R.V.I.S. graceful self-shutdown
        "SCHEDULE",          # [V9.2] Zamanlama (Iron Dome'a açıkça eklendi)
        "WEB_SEARCH",        # [V9.6] İçerik döndüren gerçek arama
        "REMEMBER",          # [V9.7] Uzun süreli hafıza kayıt
        "MAP_SHOW",          # [V10.0] Harita gösterimi
        "CHART_SHOW",        # [V10.0] Grafik/İstatistik gösterimi
        "GOOGLE_TRENDS",     # [V10.2] Google Trends araması
        "PYTHON_EXEC",       # [V15.2] Code Interpreter
        "LLM_EVAL",          # [V15.3] Cognitive Evaluator
    }

    # Sistem komutları — tool olarak LLM'e gönderilMEMELİ.
    _EXCLUDED_TOOL_TAGS = {"PLAN", "SCHEDULE"}
    def __init__(self, config, memory_manager=None, tool_registry=None):
        self.config = config
        self.memory_manager = memory_manager
        self.tool_registry = tool_registry
        self._lock = None
        
        load_dotenv()
        # [V8.1] Use config or env
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY bulunamadı.")
            
        self.client = AsyncGroq(api_key=self.api_key)
        self.model = self.config.brain_models[0]
        
        # [V6.0] Sistem promptu artık dinamik olarak oluşturuluyor
        self.system_prompt = self._build_system_prompt()
        self.chat_history = [self.system_prompt]

    def _build_system_prompt(self) -> dict:
        """
        [V9.0] Sistem promptunu dinamik olarak oluşturur.
        [GÜNCELLEME]: VISION halüsinasyonunu önleyen 'Çelik Halat' kuralı eklendi.
        
        Prompt yapısı (3 bölüm, '---' ile ayrılmış):
            [Temel Kurallar] --- [Araç Listesi] --- [Sadakat Bildirimi]
        """
        # ── BÖLÜM 1: TEMEL KURALLAR (DOKUNULMAZ) ──
        base_rules = (
            "PROTOCOL OMEGA (v9.9) - ABSOLUTE OBEDIENCE ENGINE\n"
            "1. SEN BİR SİSTEM YÖNETİCİSİSİN VE ADIN J.A.R.V.I.S. Her çıktın MUTLAKA bir protokol etiketiyle başlamalıdır. Düz metin, giriş cümleleri ('Anlaşıldı', 'İşte cevabınız') veya açıklama metinleri KESİNLİKLE YASAKTIR.\n"
            "2. SOHBET ETME. Kullanıcıyla konuşmak için SADECE [PROTOCOL: SPEAK] <mesaj> kullan. Asla [PROTOCOL: SPEAK] dışında bir metin üretme.\n"
            "3. [PROTOKOL SIZINTISI YASAĞI]: Cevapların içinde asla protokol isimlerini (örneğin: 'Lütfen [PROTOCOL: REMEMBER] kullanın' gibi) telaffuz etme. Kullanıcıya teknik komut isimlerini söyleme, sadece sonucu söyle.\n"
            "4. [ÖLÜMCÜL KURAL]: 'Adım ne?', 'Hangi takımlıyım?' gibi kişisel soruların cevabı hafızada yoksa ASLA [PROTOCOL: VISION] veya [PROTOCOL: WEB_SEARCH] kullanma. Doğrudan [PROTOCOL: SPEAK] 'Bu bilgiyi hafızamda bulamadım, lütfen bana söyleyin' de.\n"
            "5. WHATSAPP / MESAJ: 'Ablama mesaj at' veya 'Babama selam söyle' gibi WhatsApp isteklerinde YALNIZCA [PROTOCOL: WHATSAPP_MESSAGE] <kisi>|<mesaj> kullan.\n"
            "6. UYGULAMA YÖNETİMİ: 'WhatsApp'ı kapat' veya 'Youtube'u aç' dendiğinde YALNIZCA [PROTOCOL: APP_KILL/OPEN] kullan.\n"
            "7. ÇOK ADIMLI GÖREVLER (AGRESİF PLANLAMA): Birden fazla fiil veya bağlaç varsa daima [PLAN] ... [/PLAN] yapısını kullan. Her adım bir protokol olmalı.\n"
            "8. PLAN İÇİ TEMİZ PROTOKOL: Plan bloğu içinde [PROTOCOL:] prefixini kullanma, sadece protokol ismini yaz.\n"
            "9. [ZIRHLI KURAL]: ASLA 'GOOGLE_SUMMARY' gibi hayali araçlar uydurma.\n"
            "10. [VERİ AKTARIMI]: Önceki adımların sonuçları (Örn: WEB_SEARCH sonuçları) sisteme otomatik olarak kaydedilir. Senin [STEP:WEB_SEARCH] gibi etiketler yazmana KESİNLİKLE GEREK YOKTUR. Verileri okumak ve yorumlamak için sadece [PROTOCOL: LLM_EVAL] kullan.\n"
            "11. VISION KISITLAMASI: 'Araştır ve WhatsApp'tan gönder' görevlerinde VISION KESİNLİKLE KULLANILMAZ.\n"
            "12. [V9.0 - ÇELİK HALAT]: Sistem saatini öğrenmek veya geçmiş hafıza kayıtlarını bulmak için KESİNLİKLE VISION (Ekran Okuma) KULLANMA. "
            "Tarih ve saat bilgisi sana [SİSTEM DURUMU] bloğunda zaten otomatik verilir. Eğer sana sorulan geçmiş bir görev [UZUN DÖNEM HAFİZA] içinde yoksa, "
            "asla arama yapma; sadece 'Geçmiş kayıtlarımda bulunmuyor' de ve dur.\n"
            "13. UYGULAMA AÇMA KURALI: 'X'i aç', 'X'i başlat', 'X'i çalıştır' gibi komutlarda SADECE [PROTOCOL: APP_OPEN] X kullan. "
            "WhatsApp, Discord, Spotify gibi isimler geçse bile önce APP_OPEN dene. "
            "Mesaj göndermek için açıkça 'mesaj at', 'yaz', 'söyle' gibi fiiller gerekir.\n"
            "14. HATIRLATMA KURALI: 'X dakika/saat sonra hatırlat', 'alarm kur', 'hatırlatıcı ayarla' gibi zamanlama "
            "komutlarında SADECE [PROTOCOL: SCHEDULE] dakika|mesaj formatını kullan. "
            "Örnek: '5 dakika sonra mola ver diye hatırlat' → [PROTOCOL: SCHEDULE] 5|mola ver. "
            "APP_OPEN veya başka protokol KULLANMA.\n"
            "15. DOSYA/DİZİN KURALI: 'Dosyaları listele', 'belgeleri göster', 'masaüstündeki dosyalar', 'klasörü aç' gibi komutlarda SADECE [PROTOCOL: FILE_READ] <yol> kullan. "
            "Örnekler: "
            "'masaüstündeki belgeleri listele' → [PROTOCOL: FILE_READ] masaüstü, "
            "'belgeler klasörünü listele' → [PROTOCOL: FILE_READ] belgeler, "
            "'C:/Users/dosyaları göster' → [PROTOCOL: FILE_READ] C:/Users. "
            "SPEAK ile 'anlaşıldı' demek YASAKTIR, mutlaka FILE_READ çağır.\n"
            "16. ARAŞTIRMA + MESAJ KURALI: 'Araştır ve ablama/birine gönder/at' gibi "
            "çok adımlı komutlarda MUTLAKA [PLAN] bloğu kullan. Ancak KİME gönderileceği AÇIKÇA belirtilmemişse (örn: sadece 'araştırıp söyler misin' denmişse) ASLA WHATSAPP_MESSAGE kullanma! Yalnızca WEB_SEARCH kullan. "
            "[KRİTİK] 'Araştır ve gönder/mesaj at' akışında WEB_SEARCH kullan, GOOGLE_SEARCH DEĞİL. "
            "Örnek 1: 'X araştır ve ablama gönder' → "
            "[PLAN] 1. WEB_SEARCH X 2. WHATSAPP_MESSAGE ablam|[STEP:WEB_SEARCH] [/PLAN] "
            "Örnek 2: 'X araştırıp söyler misin' → Sadece [PROTOCOL: WEB_SEARCH] X "
            "Function calling KULLANMA, düz metin [PLAN] bloğu üret.\n"
            "17. STEAM KURALI: 'Steam'den X aç', 'X oyununu başlat' komutlarında [PROTOCOL: STEAM_LAUNCH] oyun_adı kullan.\n"
            "18. GÜÇ KURALI: 'Bilgisayarı kapat', 'PC'yi kapat', 'Windows'u kapat', 'yeniden başlat' gibi BİLGİSAYARIN FİZİKSEL kapatılması için [PROTOCOL: SYSTEM_POWER] kapat/yeniden_başlat kullan. Onay gelmeden çalıştırma.\n"
            "19. EPİC GAMES KURALI: 'Rocket League aç', 'Fortnite başlat' gibi komutlarda [PROTOCOL: EPIC_LAUNCH] oyun_adı kullan.\n"
            "20. SEKME KAPATMA KURALI: 'Az önce açtığın sekmeyi kapat', 'Arama sekmesini kapat' komutlarında [PROTOCOL: CLOSE_LAST_TAB] kullan.\n"
            "21. [KRİTİK] JARVIS KENDİ KAPATMA KURALI: 'Kapat kendini', 'J.A.R.V.I.S.'i kapat', 'programı kapat', 'görüşmek üzere kapat', 'çıkış yap', 'uygulamayı kapat', 'kendini sonlandır' gibi J.A.R.V.I.S. PROGRAMINI hedef alan komutlarda SADECE [PROTOCOL: SYSTEM_SHUTDOWN] kullan. "
            "NOT: SYSTEM_POWER=bilgisayarın fiziksel kapatılması. SYSTEM_SHUTDOWN=J.A.R.V.I.S. programının kendini kapatması. Parametre GEREKMİYOR.\n"
            "22. [ÖLÜMCÜL KURAL - KAPANIŞ ETİKETİ]: [PLAN] bloğunu MUTLAKA tam olarak [/PLAN] ile bitir. "
            "[/PROTOCOL], [/PROTOCOL: PLAN], [/PROTOCOL PLAN], ./PROTOCOL PLAN, /PROTOCOL PLAN, [PLAN_END] gibi UYDURMA kapanış etiketleri KESİNLİKLE YASAKTIR. "
            "Yanlış etiket sistemin bozulmasına yol açar. Tek geçerli kapanış SADECE 7 KARAKTERDİR: [/PLAN]\n"
            "23. [GÖRÜNMEZ MOD vs GÖRÜNÜR MOD KURALI]:\n"
            "   a) Kullanıcı 'Messi kaç yaşında?', 'Hava nasıl?' gibi bir soru sorarsa veya sana bilgi sorarsa DAİMA arka planda çalışan [PROTOCOL: WEB_SEARCH] <sorgu> kullan. Bu araç görünmezdir ve doğrudan sana veri sağlar.\n"
            "   b) Kullanıcı ÖZELLİKLE 'Google'da arat', 'tarayıcıda aç', 'ekranda göster' derse SADECE o zaman [PROTOCOL: GOOGLE_SEARCH] <sorgu> kullan. Bu araç görünür bir sekme açar.\n"
            "   Gereksiz yere sekmeler (GOOGLE_SEARCH) açmak KESİNLİKLE YASAKTIR.\n"
            "24. UZUN SÜRELİ HAFIZA KURALI: Kullanıcı kendisi, sevdiği şeyler, tercihleri veya hayatı hakkında kalıcı bir bilgi verdiğinde bunu AÇIKÇA kaydetmek için [PROTOCOL: REMEMBER] <bilgi> kullan. Örnek: 'Benim adım Oğuz' -> [PROTOCOL: REMEMBER] Kullanıcının adı Oğuz. Yalnızca önemli kişisel bilgileri kaydet.\n"
            "25. HARİTA KURALI: Kullanıcı bir konumun nerede olduğunu sorduğunda, koordinatlarını istediğinde veya 'haritada göster' dediğinde SADECE [PROTOCOL: MAP_SHOW] <lat>|<lon>|<title>|<zoom> kullan. "
            "Örnek: 'İstanbul nerede?' -> [PROTOCOL: MAP_SHOW] 41.0082|28.9784|İstanbul|10. "
            "Eğer koordinatları bilmiyorsan önce WEB_SEARCH ile öğren.\n"
            "26. GRAFİK KURALI: Kullanıcı istatistiksel bir veri sorduğunda veya bir karşılaştırma istediğinde verileri görselleştirmek için [PROTOCOL: CHART_SHOW] <json_data>|<title>|<type> kullan. "
            "Type şunlardan biri olmalı: 'bar', 'line', 'pie', 'area'. JSON şeması: {\"labels\": [\"A\", \"B\"], \"values\": [10, 20], \"ylabel\": \"Birim\"}. "
            "Örnek: 'Doların son 3 gününü grafik yap' -> [PROTOCOL: CHART_SHOW] {\"labels\":[\"Pzt\",\"Sal\",\"Çar\"],\"values\":[32,32.5,33],\"ylabel\":\"TL\"}|Dolar Kuru|line\n"
            "27. GOOGLE TRENDS KURALI: Kullanıcı özellikle bir şeyin 'ne kadar trend', 'popülaritesi ne durumda' veya 'Google Trends'te araştır' dediğinde SADECE [PROTOCOL: GOOGLE_TRENDS] <sorgu> kullan. Örnek: 'bed wars ne kadar trend' -> [PROTOCOL: GOOGLE_TRENDS] bed wars.\n"
            "28. [ÖZ FARKINDALIK KURALI]: 'Neler yapabilirsin', 'Yeteneklerin neler', 'Sen kimsin' gibi senin ÖZ varlığını ve özelliklerini sorgulayan komutlarda KESİNLİKLE hiçbir arama (GOOGLE_SEARCH, WEB_SEARCH vs.) kullanma! Sadece aşağıda listelenen SADAKAT VE YETENEK HARİTASI'nı okuyup [PROTOCOL: SPEAK] ile kendi kelimelerinle özetle.\n"
            "29. [HESAPLAMA KURALI]: Matematik ve hesaplama görevlerinde İKİ farklı aracın var:\n"
            "A) Eğer internetten veri çekip (WEB_SEARCH) bu veriler üzerinden hesaplama/mantık yürüteceksen KESİNLİKLE [PROTOCOL: LLM_EVAL] <soru> kullan. PYTHON_EXEC kullanma! Örnek:\n"
            "[PLAN]\n"
            "1. WEB_SEARCH Messi güncel gol sayısı\n"
            "2. WEB_SEARCH Ronaldo güncel yaşı\n"
            "3. LLM_EVAL Messi'nin golü ile Ronaldo'nun yaşını topla\n"
            "[/PLAN]\n"
            "B) Eğer kullanıcı senden anlık bir HESAPLAMA istiyorsa (\"5+3 kaç eder\", \"asal sayıları bul\") → doğrudan [PROTOCOL: PYTHON_EXEC] kullan:\n"
            "  Örnek: '15 üstüne 27 ekle' → [PROTOCOL: PYTHON_EXEC] print(15+27)\n"
            "  Örnek: 'Fibonacci serisi' → [PROTOCOL: PYTHON_EXEC] a,b=0,1\\nfor _ in range(10): print(a,end=' '); a,b=b,a+b\n"
            "[PYTHON_EXEC İÇİN ÖLÜMCÜL KURALLAR]:\n"
            "  - KESİNLİKLE `input()` KULLANMA! Bu ortamda kullanıcıdan girdi alınamaz.\n"
            "  - Her zaman `print()` ile sonucu ekrana yaz.\n"
            "30. [ÖLÜMCÜL KURAL - PROGRAM/UYGULAMA YAZMA]: Eğer kullanıcı senden bir UYGULAMA, PROGRAM veya ARAYÜZ (GUI) OLUŞTURMANI istiyorsa (\"hesap makinesi yap\", \"program yaz\", \"araç oluştur\", \"oyun yap\") →\n"
            "   Bunu PYTHON_EXEC ile YAPAMAZSIN! PYTHON_EXEC sadece gizli matematik hesaplamaları içindir.\n"
            "   Program yaratmak için KESİNLİKLE [PROTOCOL: FILE_WRITE] kullanıp Masaüstüne çalışan bir Python dosyası yazmalısın. Örnek:\n"
            "   Kullanıcı: 'Hesap makinesi yap'\n"
            "   Senin Yanıtın: [PROTOCOL: FILE_WRITE] C:/Users/proog/OneDrive/Masaüstü/hesap_makinesi.py|import tkinter as tk\\nroot=tk.Tk()\\nroot.title('Hesap Makinesi')\\n#... (arayüz kodları) ...\\nroot.mainloop()\n"
            "31. [ZAMAN FARKINDALIĞI KURALI]: WEB_SEARCH kullanırken, EĞER kullanıcı 'güncel', 'şu an', 'bugün' gibi kelimeler kullanıyorsa sorguya '2026' ekle. EĞER kullanıcı zaten geçmiş bir yıl (örn: 2011, 2015) belirtmişse, sorguya ASLA 2026 ekleme, sadece o geçmiş yılı kullan (Örn: '2011 dolar kuru').\n"
            "32. [DOSYA DÜZENLEME KURALI]: Kullanıcı var olan bir dosyayı değiştirmeni, düzenlemeni veya fixlemeni istediğinde ASLA kodu sadece sohbette gösterme!\n"
            "   Doğrudan [PROTOCOL: FILE_WRITE] dosya_yolu|yeni_tam_kod şeklinde dosyayı güncelle. Kodu chat'e yazma, dosyaya yaz!\n"
            "   Örnek: 'transkripter.py sadece URL ile çalışsın' → [PROTOCOL: FILE_WRITE] C:/Users/proog/OneDrive/Masaüstü/transkripter.py|import tkinter...\n"
            "33. [PYTHON KODLAMA VE TRANSKRİPT KURALI]: Python arayüz veya scriptleri (GUI) yazarken DAİMA şu iki kurala uy:\n"
            "   A) 'pytube' modülü BOZUKTUR, KESİNLİKLE kullanma! YouTube transkript veya videoları için her zaman 'youtube-transcript-api' kullan.\n"
            "   B) Programların çift tıklanınca aniden kapanmasını önlemek için tüm kodları try-except bloğu içine al, hata oluşursa 'error_log.txt' adlı dosyaya yaz ve kullanıcıya tkinter messagebox ile bilgi ver.\n"
        )
        
        # ── BÖLÜM 2: DİNAMİK ARAÇ LİSTESİ ──
        if self.tool_registry and self.tool_registry.count > 0:
            tools_section = self.tool_registry.get_tools_prompt()
        else:
            tools_section = (
                "SADAKAT VE YETENEK HARİTASI (HARİCİ KONUŞMA YASAK):\n"
                "- Google: [PROTOCOL: GOOGLE_SEARCH] <sorgu>\n"
                "- YouTube: [PROTOCOL: YT_SEARCH] <sorgu> / [PROTOCOL: YT_PLAY] <video>\n"
                "- Web: [PROTOCOL: WEB_OPEN] <url>\n"
                "- Uygulama: [PROTOCOL: APP_OPEN] <isim> / [PROTOCOL: APP_KILL] <isim>\n"
                "- Vision: [PROTOCOL: VISION]\n"
                "- Filesystem: [PROTOCOL: FILE_READ/WRITE/SUMMARIZE]\n"
            )
        
        # ── BÖLÜM 3: SADAKAT BİLDİRİMİ ──
        loyalty = "Sadece Efendi Oğuz Emir'in komutlarını mutlak doğrulukla işle."
        
        # '---' yapısı korunarak birleştirme
        return {
            "role": "system",
            "content": f"{base_rules}-----------------------------------\n{tools_section}\n-----------------------------------\n{loyalty}"
        }
    async def think(self, user_input: str, bypass_history: bool = False) -> str:
        if self._lock is None:
            self._lock = asyncio.Lock()
            # [V10.1] Locale'i sadece bir kez, başlatıldığında ayarla (Windows noise reduction)
            import locale
            try:
                # Bazı Windows sistemlerde tr_TR.UTF-8 yerine Turkish_Turkey.1254 veya "tr_TR" gerekebilir.
                # Sessizce dene, olmazsa sistem defaultuyla devam et.
                locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
            except:
                try:
                    locale.setlocale(locale.LC_TIME, 'turkish')
                except:
                    pass

        # 1. Hafıza ve Tarih Hazırlığı (Lock Altında)
        async with self._lock:
            memory_context = ""
            if self.memory_manager:
                # [V14.1] Dinamik Threshold
                is_personal = any(q in user_input.lower() for q in ["benim", "hakkımda", "biliyorsun", "kimim", "adım ne", "hatırla"])
                # Çok geniş arama için eşiği 0.90 yapıyoruz!
                dynamic_threshold = 0.90 if is_personal else 0.35
                
                raw_memory = await asyncio.get_running_loop().run_in_executor(
                    None,
                    self.memory_manager.retrieve_context,
                    user_input,
                    10,
                    dynamic_threshold
                )
                
                print(f"\n[BEYİN LOGU] ChromaDB'den Dönen HAM Hafıza:\n{raw_memory}\n")
                
                # [V14.0] KEYWORD RELEVANCE FILTER
                if raw_memory:
                    # EĞER KİŞİSEL SORUYSA FİLTREYİ KESİNLİKLE KULLANMA, DOĞRUDAN RAW VERİYİ VER!
                    if is_personal:
                        memory_context = raw_memory
                        print(f"\n[BEYİN LOGU] Kişisel soru algılandı. Filtre atlandı. LLM'e gidecek metin:\n{memory_context}\n")
                    else:
                        memory_context = self._filter_relevant_memory(user_input, raw_memory)
                        print(f"\n[BEYİN LOGU] Filtrelenmiş Hafıza:\n{memory_context}\n")
            
            from datetime import datetime
            now_str = datetime.now().strftime("%d %B %Y, %A - %H:%M")

            system_injection = f"[SİSTEM DURUMU]\nŞu anki tarih ve saat: {now_str}\n\n[UZUN DÖNEM HAFİZA]\n"
            if memory_context and memory_context.strip():
                system_injection += f"{memory_context}\n"
                system_injection += "SİSTEM UYARISI: Yukarıdaki hafıza kayıtları KESİN VE GERÇEKTİR. Kullanıcı senin hafızanda ne olduğunu soruyorsa VEYA kendi hakkında (adı, tutkusu vb.) bir şey soruyorsa, yukarıdaki [UZUN DÖNEM HAFİZA] metnini KESİNLİKLE kullan! 'Bilmiyorum' deme!\n"
            else:
                system_injection += "SİSTEM UYARISI: HAFIZA BOŞ veya ALAKALI KAYIT BULUNAMADI! Kullanıcının kişisel bilgilerini (adı vb.) soruyorsa 'Bu bilgiyi hafızamda bulamadım, lütfen bana söyleyin' de.\n"
            system_injection += "[/HAFİZA]\n"

            if hasattr(self.memory_manager, 'pattern_extractor'):
                patterns = self.memory_manager.pattern_extractor.get_active_patterns()
                if patterns:
                    system_injection += f"[ÖĞRENİLEN KURALLAR]\n{patterns}\n"

            # [V14.0] Öğrenilmiş stratejileri enjekte et
            if hasattr(self, '_adaptive_learner_ref') and self._adaptive_learner_ref:
                learned_rules = self._adaptive_learner_ref.get_learned_rules_prompt(limit=8)
                if learned_rules:
                    system_injection += f"\n{learned_rules}\n"

            if bypass_history:
                messages = [self.system_prompt]
            else:
                messages = list(self.chat_history)
            
            messages.insert(1, {
                "role": "system",
                "content": system_injection
            })
            messages.append({"role": "user", "content": user_input})

        # 2. Groq API Çağrısı (Lock Dışında - Uzun süren işlem)
        if memory_context:
            print(f"\n[BEYİN LOGU] Hafızadan Çekilen Veri (Threshold 0.25, Filtered):\n{memory_context}\n")

        api_kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": getattr(self.config, "max_tokens", 2048),
            "temperature": getattr(self.config, "temperature", 0.3),
        }

        use_tools = getattr(self.config, "function_calling_enabled", False)
        if use_tools and self.tool_registry and self.tool_registry.count > 0:
            tools_payload = []
            for tool in self.tool_registry._tools.values():
                if tool.protocol_tag in self._EXCLUDED_TOOL_TAGS:
                    continue
                properties = {}
                for k, v in tool.parameters.items():
                    if isinstance(v, dict):
                        properties[k] = {"type": v.get("type", "string"), "description": str(v.get("description", ""))}
                    else:
                        properties[k] = {"type": "string", "description": str(v)}
                
                tools_payload.append({
                    "type": "function",
                    "function": {
                        "name": tool.protocol_tag,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": list(properties.keys())
                        }
                    }
                })
            if tools_payload:
                api_kwargs["tools"] = tools_payload
                api_kwargs["tool_choice"] = "auto"

        # Groq API Çağrısı — Rate Limit / Fallback korumalı döngü
        choice = None
        response = None
        last_error = None
        
        from groq import RateLimitError, APIConnectionError, APIError
        import groq

        for i, current_model in enumerate(self.config.brain_models):
            api_kwargs["model"] = current_model
            
            # [V15.5] Küçük modellere düşerken history'yi agresif kırp
            # 8b modelin Groq free tier TPM limiti 6000 — sığması için
            if "8b" in current_model:
                # Sadece system prompt + son 2 mesaj + yeni user input bırak
                trimmed = [messages[0]]  # system prompt
                if len(messages) > 3:
                    trimmed += messages[-2:]  # son user+assistant çifti
                trimmed.append(messages[-1])  # yeni user input (zaten son eleman)
                # Duplicate kontrolü
                seen = set()
                unique = []
                for m in trimmed:
                    key = m.get("content", "")[:50]
                    if key not in seen:
                        seen.add(key)
                        unique.append(m)
                api_kwargs["messages"] = unique
                api_kwargs["max_tokens"] = min(api_kwargs.get("max_tokens", 2048), 1024)
                print(f"[BEYİN LOGU] 8b fallback: history {len(messages)} → {len(unique)} msg, max_tokens=1024")
            
            try:
                response = await self.client.chat.completions.create(**api_kwargs)
                choice = response.choices[0]
                break # Başarılı olduysa döngüden çık
            except RateLimitError as e:
                last_error = e
                continue
            except (APIConnectionError, APIError) as e:
                last_error = e
                continue
            except Exception as e:
                raise e

        # Hiçbir model başarılı olamadıysa
        if choice is None:
            print(f"[BEYİN LOGU] Tüm fallback modeller tükendi. Son hata: {last_error}")
            return "RATE_LIMIT_ALL"

        # 3. Yanıtı İşle ve Tarihçeyi Güncelle (Tekrar Lock Altında)
        async with self._lock:
            import json
            if getattr(choice.message, "tool_calls", None):
                tool_call = choice.message.tool_calls[0]
                tag = tool_call.function.name

                if tag not in self.VALID_PROTOCOLS:
                    fallback_content = getattr(choice.message, "content", None) or ""
                    if fallback_content.strip():
                        reply = fallback_content
                    else:
                        retry_kwargs = api_kwargs.copy()
                        # Fallback content boş geldiğinde uydurma etiketi tekrar tekrar üretmesini engellemek için:
                        # Tekrar denerken aynı listeyi dolaşıp şansımızı deneriz, 
                        # ancak pratikte bu fallback nadiren istenir.
                        try:
                            retry_resp = await self.client.chat.completions.create(**retry_kwargs)
                            reply = retry_resp.choices[0].message.content or ""
                        except Exception:
                            reply = "[PROTOCOL: SPEAK] Efendim, bu isteği nasıl karşılayacağımı bilemedim."
                else:
                    try:
                        args_dict = json.loads(tool_call.function.arguments)
                        if tag == "WHATSAPP_MESSAGE" and "kisi" in args_dict and "mesaj" in args_dict:
                            arg_str = f"{args_dict['kisi']}|{args_dict['mesaj']}"
                        else:
                            arg_str = " ".join(str(v) for v in args_dict.values())
                    except Exception:
                        arg_str = ""
                    reply = f"[PROTOCOL: {tag}] {arg_str}".strip()
            else:
                reply = choice.message.content or ""

            # 4. Sohbet Geçmişini Güncelle
            if not bypass_history:
                self.chat_history.append({"role": "user", "content": user_input})
                self.chat_history.append({"role": "assistant", "content": reply})
                
                # [V10.2 FIX] Geçmişi sınırla (Payload Too Large Hatasını Önler)
                # [V15.5] Token tasarrufu — Groq free tier TPM limiti için agresif kırpma
                if len(self.chat_history) > 7:
                    self.chat_history = [self.chat_history[0]] + self.chat_history[-6:]
            
            return reply

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [V14.0] MEMORY RELEVANCE FILTER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _filter_relevant_memory(user_input: str, memory_text: str) -> str:
        """
        [V14.0] Hafıza Zehirlenmesi Önleyici
        
        Hafızadan çekilen her satırı kullanıcı girdisiyle keyword overlap
        kontrolünden geçirir. Hiç ortak kelimesi olmayan satırları atar.
        
        Bu, eski WhatsApp görevlerinin veya alakasız episodic kayıtların
        mevcut bağlamı zehirlemesini önler.
        """
        if not memory_text or not user_input:
            return memory_text
        
        # Kullanıcı girdisindeki anlamlı kelimeleri çıkar (3+ karakter)
        stop_words = {
            'bir', 'bir', 'bu', 'şu', 'da', 'de', 'mi', 'mı', 'mu', 'mü',
            've', 'ile', 'için', 'ben', 'sen', 'bana', 'sana', 'beni', 'seni',
            'var', 'yok', 'ne', 'nasıl', 'lütfen', 'eder', 'olur', 'olan',
            'the', 'is', 'are', 'and', 'or', 'can', 'you', 'this', 'that',
            'gibi', 'kadar', 'daha', 'çok', 'her', 'hiç', 'ama', 'fakat',
            'sonra', 'önce', 'şimdi', 'şey', 'biraz', 'adında', 'adlı',
        }
        
        input_words = set()
        for word in re.findall(r'[\wçğıöşüÇĞİÖŞÜ]+', user_input.lower()):
            if len(word) >= 3 and word not in stop_words:
                input_words.add(word)
        
        if not input_words:
            return memory_text
            
        # [HACK] Eğer kullanıcı doğrudan kendini veya hafızayı soruyorsa, filtreyi atla
        self_queries = ["benim", "hakkımda", "biliyorsun", "kimim", "adım ne", "hatırla"]
        if any(q in user_input.lower() for q in self_queries):
            return memory_text
        
        # Her hafıza satırını kontrol et
        filtered_lines = []
        for line in memory_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            line_words = set()
            for word in re.findall(r'[\wçğıöşüÇĞİÖŞÜ]+', line.lower()):
                if len(word) >= 3:
                    line_words.add(word)
            
            # En az 1 ortak anlamlı kelime olmalı
            overlap = input_words & line_words
            if overlap:
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines) if filtered_lines else ""

    async def check_connection(self) -> bool:
        """[V5.9] API bağlantısının sağlıklı olup olmadığını test eder."""
        try:
            model_to_test = getattr(self.config, "ping_model", None) or self.model
            # Çok basit bir test çağrısı
            await self.client.chat.completions.create(
                model=model_to_test,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                timeout=3.0
            )
            return True
        except Exception:
            return False