import asyncio
import requests
import logging
import re
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.AnalizProTool")

class AnalizProTool(BaseTool):
    name = "analiz_pro_tool"
    description = "YouTube analiz uygulaması ile haberleşir, kanal raporu ve trend analizi yapar."
    protocol_tag = "ANALIZ_PRO"
    domain = "system"
    latency_ms = 5000
    reliability_score = 1.0
    parameters = {"query": {"type": "string", "description": "Analiz komutu"}}
    pre_speak = "Analiz Pro veritabanına bağlanıyorum Efendim."

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        query = params.get("query", "").lower()
        loop = asyncio.get_running_loop()

        # Aktif kullanıcıyı dinamik olarak çek (Hardcoded user_id=1 sorununu çözer)
        def _get_active_user():
            try:
                res = requests.get("http://127.0.0.1:8000/api/session", timeout=3)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("session") and data["session"].get("user_id"):
                        return data["session"]["user_id"]
            except:
                pass
            return 1 # Fallback
            
        active_user_id = await loop.run_in_executor(None, _get_active_user)

        # 1. Rapor / Özet Çekme
        if any(w in query for w in ["rapor", "özet", "son durum", "skor", "verimlilik"]):
            try:
                def _fetch_profile():
                    return requests.get(f"http://127.0.0.1:8000/api/profile?user_id={active_user_id}", timeout=10)
                
                resp = await loop.run_in_executor(None, _fetch_profile)
                if resp.status_code == 200:
                    data = resp.json()
                    recent = data.get("recent_analyses", [])
                    
                    # KISS 4.0: Önce tüm kanalları çek, hangisinin sorulduğunu kesin bul
                    def _fetch_channels():
                        return requests.get(f"http://127.0.0.1:8000/channels?user_id={active_user_id}", timeout=5)
                    
                    ch_resp = await loop.run_in_executor(None, _fetch_channels)
                    target_channel_name = None
                    
                    if ch_resp.status_code == 200:
                        channels = ch_resp.json()
                        query_clean = query.replace(" ", "").lower()
                        # Cümlede geçen kanalı bul
                        for ch in channels:
                            c_name = ch.get("name", "")
                            if c_name.replace(" ", "").lower() in query_clean:
                                target_channel_name = c_name
                                break
                    
                    if target_channel_name:
                        # Kanal bulundu, bu kanala ait analiz var mı bak
                        ch_analyses = [r for r in recent if r.get("channel", "").lower() == target_channel_name.lower()]
                        if not ch_analyses:
                            return ToolResult(
                                success=True, verified=True, 
                                message=f"{target_channel_name} kanalı için henüz analiz yapılmamış.", 
                                speak=f"Efendim, {target_channel_name} kanalı sistemde kayıtlı ancak henüz hiçbir videosunu analiz etmemişsiniz."
                            )
                        target_analysis = ch_analyses[0]
                    else:
                        if not recent:
                            return ToolResult(success=True, verified=True, message="Hiç analiz kaydı bulunamadı.", speak="Efendim, Analiz Pro'da henüz hiçbir video analizi bulunmuyor.")
                        # Cümlede kanal adı yoksa veya bulunamadıysa en son analizi ver
                        target_analysis = recent[0]
                        
                    v_name = target_analysis.get("video", "Bilinmeyen Video")
                    v_score = target_analysis.get("score", 0)
                    c_name = target_analysis.get("channel", "Kanalınız")
                    
                    msg = f"📊 **{c_name} Son Analiz:**\n🎬 Video: '{v_name}'\n⭐ Skor: {v_score}/10"
                    speak_msg = f"Efendim, {c_name} kanalındaki son videonuz olan '{v_name}' için analiz skoru 10 üzerinden {v_score} olarak belirlenmiş."
                        
                    return ToolResult(success=True, verified=True, message=msg, speak=speak_msg, data=data)
                return ToolResult(success=False, verified=False, error="API_Error", message="Rapor çekilemedi.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message="Bağlantı hatası.")

        # 2. Trend / Rakip Taraması
        elif any(w in query for w in ["trend", "araştır", "rakip", "fikir", "bul"]):
            # KISS: Tüm noktalama işaretlerini ve J.A.R.V.I.S. kelimesini acımasızca sil
            clean_q = query.replace("j.a.r.v.i.s.", "").replace("jarvis", "")
            clean_q = re.sub(r'[^\w\s]', ' ', clean_q)
            
            remove_words = {"analiz", "pro", "uygulaması", "üzerinden", "trendlerini", "trendleri", "trend", "araştır", "rakip", "fikir", "bul", "bana", "için", "hakkında", "lütfen", "dan", "den", "yap", "çek", "nedir"}
            
            # Sadece temiz kelimeleri tut
            kw_words = [w for w in clean_q.split() if w not in remove_words]
            kw = " ".join(kw_words).strip()
            
            if not kw: kw = "YouTube"
                
            try:
                def _fetch_trend():
                    payload = {"keyword": kw, "user_id": active_user_id, "lang": "tr"}
                    return requests.post("http://127.0.0.1:8000/api/content_finder", json=payload, timeout=45)
                
                resp = await loop.run_in_executor(None, _fetch_trend)
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" in data:
                        return ToolResult(success=False, verified=False, error="API_Error", message=data["error"], speak="Efendim, arama sırasında bir hata oluştu.")
                    
                    videos = data.get("videos", [])
                    outliers = [v for v in videos if v.get("is_outlier")]
                    
                    msg = f"🔍 **'{kw}' Trend Analizi:**\n"
                    speak_msg = f"Efendim, '{kw}' için trend analizi tamamlandı. "
                    
                    if outliers:
                        best = outliers[0]
                        msg += f"🔥 **Patlayan Video:** {best['title']} ({best['channel']}) - Hız: {best['view_velocity']} izlenme/gün\n"
                        speak_msg += f"Şu an {best['channel']} kanalının bir videosu normalden çok daha hızlı izleniyor. Videoyu tarayıcınızda açıyorum. "
                        
                        # Videoyu tarayıcıda aç
                        try:
                            import webbrowser
                            video_url = best.get("url", "")
                            if video_url:
                                await loop.run_in_executor(None, webbrowser.open, video_url)
                        except Exception as e:
                            logger.warning(f"Video açılamadı: {e}")
                    else:
                        speak_msg += "Dikkat çeken anormal bir yükseliş bulunamadı. "
                        
                    ai_ideas = data.get("ai_ideas", [])
                    if ai_ideas:
                        msg += f"\n💡 **AI Önerisi:** {ai_ideas[0].get('title')}\n🎣 **Kanca:** {ai_ideas[0].get('hook')}"
                        speak_msg += "Ayrıca bu trende uygun yeni bir video fikri ve kanca cümlesi ekrana yansıtıldı."
                        
                    return ToolResult(success=True, verified=True, message=msg, speak=speak_msg, data=data)
                return ToolResult(success=False, verified=False, error="API_Error", message="Trend analizi yapılamadı.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message="Bağlantı hatası.")

        # 3. Default Ping
        else:
            try:
                def _ping():
                    return requests.get("http://127.0.0.1:8000/health", timeout=5)
                response = await loop.run_in_executor(None, _ping)
                if response.status_code == 200:
                    return ToolResult(success=True, verified=True, message="Analiz Pro ile bağlantı başarılı!", speak="Analiz uygulaması ile bağlantı kuruldu Efendim.")
                return ToolResult(success=False, verified=False, error="ConnFailed", message="Sunucu yanıt vermedi.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message="Bağlantı kurulamadı.")
