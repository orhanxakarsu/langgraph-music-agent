"""
WhatsApp Webhook Handler
========================
WhatsApp'tan gelen mesajları alır ve System Supervisor'a iletir.
"""

import os
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from langgraph.types import Command
from system_supervisor import create_system_supervisor
from state import create_initial_state

app = Flask(__name__)

# Statik dosya dizinleri
ARTIFACTS_DIR = os.path.abspath("artifacts")
os.makedirs(f"{ARTIFACTS_DIR}/musics", exist_ok=True)
os.makedirs(f"{ARTIFACTS_DIR}/generated_images", exist_ok=True)
os.makedirs(f"{ARTIFACTS_DIR}/final_videos", exist_ok=True)

# Server bilgileri (Tailscale için)
SERVER_HOST = os.getenv("SERVER_HOST", "100.x.x.x")  # Tailscale IP
SERVER_PORT = os.getenv("SERVER_PORT", "5000")

# ============== DUPLICATE MESAJ KONTROLÜ ==============
# Son işlenen mesajları tut (phone -> {message_id, hash, timestamp})
processed_messages = {}
DUPLICATE_WINDOW_SECONDS = 30  # 30 saniye içinde aynı mesaj gelirse ignore et


def get_message_hash(phone: str, text: str) -> str:
    """Mesaj için unique hash oluştur"""
    content = f"{phone}:{text}"
    return hashlib.md5(content.encode()).hexdigest()


def is_duplicate_message(phone: str, text: str, message_id: str = None) -> bool:
    """
    Mesajın duplicate olup olmadığını kontrol et.
    
    Returns:
        True: Duplicate, ignore edilmeli
        False: Yeni mesaj, işlenmeli
    """
    now = datetime.now()
    msg_hash = get_message_hash(phone, text)
    
    # Eski kayıtları temizle (30 saniyeden eski)
    expired_phones = []
    for p, data in processed_messages.items():
        if now - data['timestamp'] > timedelta(seconds=DUPLICATE_WINDOW_SECONDS):
            expired_phones.append(p)
    for p in expired_phones:
        del processed_messages[p]
    
    # Bu telefon için kayıt var mı?
    if phone in processed_messages:
        prev = processed_messages[phone]
        
        # Aynı message_id mi?
        if message_id and prev.get('message_id') == message_id:
            print(f"   🔄 Duplicate (same ID): {message_id}")
            return True
        
        # Aynı hash mi ve 30 saniye içinde mi?
        if prev['hash'] == msg_hash:
            time_diff = (now - prev['timestamp']).total_seconds()
            if time_diff < DUPLICATE_WINDOW_SECONDS:
                print(f"   🔄 Duplicate (same hash, {time_diff:.1f}s ago)")
                return True
    
    # Yeni mesaj - kaydet
    processed_messages[phone] = {
        'message_id': message_id,
        'hash': msg_hash,
        'timestamp': now
    }
    
    return False


# Supervisor'ı başlat
print("🚀 System Supervisor başlatılıyor...")
supervisor = create_system_supervisor()
workflow = supervisor.workflow
print("✅ System Supervisor hazır!")


# ============== STATIC FILE ROUTES ==============

@app.route('/files/music/<filename>')
def serve_music(filename):
    """Müzik dosyalarını sun"""
    return send_from_directory(f"{ARTIFACTS_DIR}/musics", filename)

@app.route('/files/image/<filename>')
def serve_image(filename):
    """Görsel dosyalarını sun"""
    return send_from_directory(f"{ARTIFACTS_DIR}/generated_images", filename)

@app.route('/files/video/<filename>')
def serve_video(filename):
    """Video dosyalarını sun"""
    return send_from_directory(f"{ARTIFACTS_DIR}/final_videos", filename)


def get_file_url(file_path: str) -> str:
    """Dosya yolundan URL oluştur"""
    if not file_path:
        return None
    
    filename = os.path.basename(file_path)
    
    if "musics" in file_path:
        return f"http://{SERVER_HOST}:{SERVER_PORT}/files/music/{filename}"
    elif "generated_images" in file_path:
        return f"http://{SERVER_HOST}:{SERVER_PORT}/files/image/{filename}"
    elif "final_videos" in file_path:
        return f"http://{SERVER_HOST}:{SERVER_PORT}/files/video/{filename}"
    else:
        return None


# Supervisor'a URL fonksiyonunu ver
supervisor.get_file_url = get_file_url


@app.route('/webhook', methods=['POST'])
def webhook():
    """WhatsApp webhook - Kullanıcıdan mesaj geldiğinde tetiklenir"""
    
    webhook_data = request.get_json()
    
    # Mesajı parse et
    parsed = supervisor.message_helper.parse_webhook(webhook_data)
    
    if not parsed:
        return jsonify({"status": "ignored"}), 200
    
    phone = parsed['phone']
    text = parsed['text']
    message_id = parsed.get('message_id')  # Webhook'tan gelen mesaj ID
    
    # ============== DUPLICATE KONTROLÜ ==============
    if is_duplicate_message(phone, text, message_id):
        return jsonify({"status": "duplicate_ignored"}), 200
    
    print("\n" + "=" * 60)
    print("📥 YENİ MESAJ")
    print(f"📱 Telefon: {phone}")
    print(f"💬 Mesaj: {text}")
    print("=" * 60)
    
    # Thread ID olarak telefon numarasını kullan
    config = {"configurable": {"thread_id": phone}}
    
    try:
        # Mevcut state'i kontrol et
        current_state = workflow.get_state(config)
        
        print(f"\n📊 Mevcut State:")
        print(f"   Next: {current_state.next if current_state.next else 'None'}")
        
        # Eğer workflow interrupt durumundaysa (wait_user veya music_selection_handler)
        if current_state.next:
            interrupted_nodes = current_state.next
            print(f"   Interrupted at: {interrupted_nodes}")
            
            if 'wait_user' in interrupted_nodes or 'music_selection_handler' in interrupted_nodes:
                print("\n🔄 Workflow RESUME ediliyor...")
                
                # Resume ile kullanıcı mesajını gönder
                result = workflow.invoke(
                    Command(resume=text),
                    config=config
                )
                
                print(f"✅ Workflow resume sonucu alındı")
                print(f"   Stage: {result.get('current_stage', 'N/A')}")
            else:
                # Workflow başka bir node'da çalışıyor (örn: music_generator)
                # Kullanıcıya bilgi ver ve mesajı ignore et
                print(f"⏳ Workflow çalışıyor: {interrupted_nodes}")
                print(f"   Kullanıcı mesajı beklemeye alındı")
                
                try:
                    supervisor.message_helper.send_message(
                        phone,
                        "⏳ Şu anda işlem devam ediyor, biraz bekle... Bitince sana haber vereceğim! 🎵"
                    )
                except:
                    pass
                
                return jsonify({"status": "processing_in_progress"}), 200
        
        else:
            print("\n🆕 Yeni Workflow başlatılıyor...")
            
            # Yeni state oluştur
            initial_state = create_initial_state(phone, text)
            
            # Workflow'u başlat
            result = workflow.invoke(initial_state, config=config)
            
            print(f"✅ Workflow başlatıldı")
            print(f"   Stage: {result.get('current_stage', 'N/A')}")
        
        return jsonify({"status": "processed"}), 200
        
    except Exception as e:
        print(f"\n❌ HATA: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Hata durumunda kullanıcıya bilgi ver
        try:
            supervisor.message_helper.send_message(
                phone, 
                "😅 Bir sorun oluştu, tekrar dener misin?"
            )
        except:
            pass
        
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "music-production-bot"
    }), 200


@app.route('/state/<phone>', methods=['GET'])
def get_state(phone):
    """Debug: Belirli bir telefon numarasının state'ini görüntüle"""
    config = {"configurable": {"thread_id": phone}}
    
    try:
        current_state = workflow.get_state(config)
        
        if current_state.values:
            # Hassas bilgileri çıkar
            safe_state = {
                "current_stage": current_state.values.get("current_stage"),
                "task_queue": current_state.values.get("task_queue"),
                "completed_tasks": current_state.values.get("completed_tasks"),
                "is_music_generated": current_state.values.get("is_music_generated"),
                "is_music_selected": current_state.values.get("is_music_selected"),
                "is_cover_generated": current_state.values.get("is_cover_generated"),
                "is_video_generated": current_state.values.get("is_video_generated"),
                "messages_count": len(current_state.values.get("messages", [])),
                "next_nodes": current_state.next
            }
            return jsonify(safe_state), 200
        else:
            return jsonify({"status": "no_state", "phone": phone}), 404
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/reset/<phone>', methods=['POST'])
def reset_conversation(phone):
    """Debug: Belirli bir telefon numarasının conversation'ını sıfırla"""
    # Not: MemorySaver ile bu işlem farklı olabilir
    # Gerçek implementasyonda checkpoint'i silmek gerekebilir
    return jsonify({
        "status": "reset_requested",
        "phone": phone,
        "note": "Full reset requires checkpoint deletion"
    }), 200


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🎵 MUSIC PRODUCTION BOT")
    print("=" * 60)
    print("Endpoints:")
    print("  POST /webhook     - WhatsApp webhook")
    print("  GET  /health      - Health check")
    print("  GET  /state/<phone> - Debug state")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)