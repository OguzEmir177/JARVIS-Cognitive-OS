import asyncio
import requests
import logging
import re
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.AnalizProTool")

class AnalizProTool(BaseTool):
    name = "analiz_pro_tool"
    description = "It communicates with the YouTube analysis application and makes channel reports and trend analysis."
    protocol_tag = "ANALIZ_PRO"
    domain = "system"
    latency_ms = 5000
    reliability_score = 1.0
    parameters = {"query": {"type": "string", "description": "Analiz komutu"}}
    pre_speak = "I'm connecting to the Analysis Pro database, Sir."

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        query = params.get("query", "").lower()
        loop = asyncio.get_running_loop()

        # Get active user dynamically (solves hardcoded user_id=1 issue)
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

        #1. Report/Summary
        if any(w in query for w in ["rapor", "summary", "son durum", "skor", "verimlilik"]):
            try:
                def _fetch_profile():
                    return requests.get(f"http://127.0.0.1:8000/api/profile?user_id={active_user_id}", timeout=10)
                
                resp = await loop.run_in_executor(None, _fetch_profile)
                if resp.status_code == 200:
                    data = resp.json()
                    recent = data.get("recent_analyses", [])
                    
                    # KISS 4.0: Pull all channels first, find out exactly which one is asked
                    def _fetch_channels():
                        return requests.get(f"http://127.0.0.1:8000/channels?user_id={active_user_id}", timeout=5)
                    
                    ch_resp = await loop.run_in_executor(None, _fetch_channels)
                    target_channel_name = None
                    
                    if ch_resp.status_code == 200:
                        channels = ch_resp.json()
                        query_clean = query.replace(" ", "").lower()
                        # Find the channel mentioned in the sentence
                        for ch in channels:
                            c_name = ch.get("name", "")
                            if c_name.replace(" ", "").lower() in query_clean:
                                target_channel_name = c_name
                                break
                    
                    if target_channel_name:
                        # Channel found, see if there is analysis for this channel
                        ch_analyses = [r for r in recent if r.get("channel", "").lower() == target_channel_name.lower()]
                        if not ch_analyses:
                            return ToolResult(
                                success=True, verified=True, 
                                message=f"No analysis has been made yet for channel {target_channel_name}.", 
                                speak=f"Sir, channel {target_channel_name} is registered in the system, but you have not analyzed any of its videos yet."
                            )
                        target_analysis = ch_analyses[0]
                    else:
                        if not recent:
                            return ToolResult(success=True, verified=True, message="No analysis records found.", speak="Sir, there is no video analysis available in Analysis Pro yet.")
                        # If there is no channel name in the sentence or it is not found, give the latest analysis
                        target_analysis = recent[0]
                        
                    v_name = target_analysis.get("video", "Bilinmeyen Video")
                    v_score = target_analysis.get("score", 0)
                    c_name = target_analysis.get("channel", "your channel")
                    
                    msg = f"📊 **{c_name} Son Analiz:**\n🎬 Video: '{v_name}'\n⭐ Skor: {v_score}/10"
                    speak_msg = f"Sir, the analysis score for your last video '{v_name}' on channel {c_name} is {v_score} out of 10."
                        
                    return ToolResult(success=True, verified=True, message=msg, speak=speak_msg, data=data)
                return ToolResult(success=False, verified=False, error="API_Error", message="The report could not be drawn.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message="Connection error.")

        #2. Trend/Competitor Scan
        elif any(w in query for w in ["trend", "research", "rakip", "fikir", "bul"]):
            # KISS: All punctuation and J.A.R.V.I.S. mercilessly delete the word
            clean_q = query.replace("j.a.r.v.i.s.", "").replace("jarvis", "")
            clean_q = re.sub(r'[^\w\s]', ' ', clean_q)
            
            remove_words = {"analiz", "pro", "application", "over", "trendlerini", "trendleri", "trend", "research", "rakip", "fikir", "bul", "bana", "for", "about", "Please", "dan", "den", "yap", "Czech", "nedir"}
            
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
                        return ToolResult(success=False, verified=False, error="API_Error", message=data["error"], speak="Sir, an error occurred during the search.")
                    
                    videos = data.get("videos", [])
                    outliers = [v for v in videos if v.get("is_outlier")]
                    
                    msg = f"🔍 **'{kw}' Trend Analizi:**\n"
                    speak_msg = f"Sir, trend analysis for '{kw}' has been completed."
                    
                    if outliers:
                        best = outliers[0]
                        msg += f"🔥 **Exploding Video:** {best['title']} ({best['channel']}) - Speed: {best['view_velocity']} views/day\n"
                        speak_msg += f"Currently a video from channel {best['channel']} is being watched much faster than usual. I open the video in your browser."
                        
                        # Open video in browser
                        try:
                            import webbrowser
                            video_url = best.get("url", "")
                            if video_url:
                                await loop.run_in_executor(None, webbrowser.open, video_url)
                        except Exception as e:
                            logger.warning(f"Failed to open video: {e}")
                    else:
                        speak_msg += "No noticeable abnormal increase was found."
                        
                    ai_ideas = data.get("ai_ideas", [])
                    if ai_ideas:
                        msg += f"\n💡 **AI Suggestion:** {ai_ideas[0].get('title')}\n🎣 **Hook:** {ai_ideas[0].get('hook')}"
                        speak_msg += "In addition, a new video idea and hook sentence in line with this trend were projected on the screen."
                        
                    return ToolResult(success=True, verified=True, message=msg, speak=speak_msg, data=data)
                return ToolResult(success=False, verified=False, error="API_Error", message="Trend analysis could not be performed.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message="Connection error.")

        # 3. Default Ping
        else:
            try:
                def _ping():
                    return requests.get("http://127.0.0.1:8000/health", timeout=5)
                response = await loop.run_in_executor(None, _ping)
                if response.status_code == 200:
                    return ToolResult(success=True, verified=True, message="Connection with Analysis Pro successful!", speak="A connection has been established with the analysis application, Sir.")
                return ToolResult(success=False, verified=False, error="ConnFailed", message="The server did not respond.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message="The connection could not be established.")
