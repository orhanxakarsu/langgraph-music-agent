"""
WhatsApp Webhook Handler
========================
Receives messages from WhatsApp and forwards them to System Supervisor.
"""

import os
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from langgraph.types import Command
from system_supervisor import create_system_supervisor
from state import create_initial_state

app = Flask(__name__)

# Static file directories
ARTIFACTS_DIR = os.path.abspath("artifacts")
os.makedirs(f"{ARTIFACTS_DIR}/musics", exist_ok=True)
os.makedirs(f"{ARTIFACTS_DIR}/generated_images", exist_ok=True)
os.makedirs(f"{ARTIFACTS_DIR}/final_videos", exist_ok=True)

# Server info (for Tailscale)
SERVER_HOST = os.getenv("SERVER_HOST", "100.x.x.x")  # Tailscale IP
SERVER_PORT = os.getenv("SERVER_PORT", "5000")

# ============== DUPLICATE MESSAGE CHECK ==============
# Keep last processed messages (phone -> {message_id, hash, timestamp})
processed_messages = {}
DUPLICATE_WINDOW_SECONDS = 30  # Ignore same message within 30 seconds


def get_message_hash(phone: str, text: str) -> str:
    """Create unique hash for message"""
    content = f"{phone}:{text}"
    return hashlib.md5(content.encode()).hexdigest()


def is_duplicate_message(phone: str, text: str, message_id: str = None) -> bool:
    """
    Check if message is duplicate.
    
    Returns:
        True: Duplicate, should be ignored
        False: New message, should be processed
    """
    now = datetime.now()
    msg_hash = get_message_hash(phone, text)
    
    # Clean old records (older than 30 seconds)
    expired_phones = []
    for p, data in processed_messages.items():
        if now - data['timestamp'] > timedelta(seconds=DUPLICATE_WINDOW_SECONDS):
            expired_phones.append(p)
    for p in expired_phones:
        del processed_messages[p]
    
    # Is there a record for this phone?
    if phone in processed_messages:
        prev = processed_messages[phone]
        
        # Same message_id?
        if message_id and prev.get('message_id') == message_id:
            print(f"   Duplicate (same ID): {message_id}")
            return True
        
        # Same hash and within 30 seconds?
        if prev['hash'] == msg_hash:
            time_diff = (now - prev['timestamp']).total_seconds()
            if time_diff < DUPLICATE_WINDOW_SECONDS:
                print(f"   Duplicate (same hash, {time_diff:.1f}s ago)")
                return True
    
    # New message - save
    processed_messages[phone] = {
        'message_id': message_id,
        'hash': msg_hash,
        'timestamp': now
    }
    
    return False


# Start Supervisor
print("Starting System Supervisor...")
supervisor = create_system_supervisor()
workflow = supervisor.workflow
print("System Supervisor ready!")


# ============== STATIC FILE ROUTES ==============

@app.route('/files/music/<filename>')
def serve_music(filename):
    """Serve music files"""
    return send_from_directory(f"{ARTIFACTS_DIR}/musics", filename)

@app.route('/files/image/<filename>')
def serve_image(filename):
    """Serve image files"""
    return send_from_directory(f"{ARTIFACTS_DIR}/generated_images", filename)

@app.route('/files/video/<filename>')
def serve_video(filename):
    """Serve video files"""
    return send_from_directory(f"{ARTIFACTS_DIR}/final_videos", filename)


def get_file_url(file_path: str) -> str:
    """Create URL from file path"""
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


# Give URL function to Supervisor
supervisor.get_file_url = get_file_url


@app.route('/webhook', methods=['POST'])
def webhook():
    """WhatsApp webhook - Triggered when user sends message"""
    
    webhook_data = request.get_json()
    
    # Parse message
    parsed = supervisor.message_helper.parse_webhook(webhook_data)
    
    if not parsed:
        return jsonify({"status": "ignored"}), 200
    
    phone = parsed['phone']
    text = parsed['text']
    message_id = parsed.get('message_id')
    
    # ============== DUPLICATE CHECK ==============
    if is_duplicate_message(phone, text, message_id):
        return jsonify({"status": "duplicate_ignored"}), 200
    
    print("\n" + "=" * 60)
    print("NEW MESSAGE")
    print(f"Phone: {phone}")
    print(f"Message: {text}")
    print("=" * 60)
    
    # Use phone number as thread ID
    config = {"configurable": {"thread_id": phone}}
    
    try:
        # Check current state
        current_state = workflow.get_state(config)
        
        print(f"\nCurrent State:")
        print(f"   Next: {current_state.next if current_state.next else 'None'}")
        
        # If workflow is in interrupt state (wait_user or music_selection_handler)
        if current_state.next:
            interrupted_nodes = current_state.next
            print(f"   Interrupted at: {interrupted_nodes}")
            
            if 'wait_user' in interrupted_nodes or 'music_selection_handler' in interrupted_nodes:
                print("\nRESUMING workflow...")
                
                # Resume with user message
                result = workflow.invoke(
                    Command(resume=text),
                    config=config
                )
                
                print(f"Workflow resume result received")
                print(f"   Stage: {result.get('current_stage', 'N/A')}")
            else:
                # Workflow running on another node (e.g. music_generator)
                # Inform user and ignore message
                print(f"Workflow running: {interrupted_nodes}")
                print(f"   User message put on hold")
                
                try:
                    supervisor.message_helper.send_message(
                        phone,
                        "Processing in progress, please wait... I'll let you know when it's done!"
                    )
                except:
                    pass
                
                return jsonify({"status": "processing_in_progress"}), 200
        
        else:
            print("\nSTARTING new workflow...")
            
            # Create new state
            initial_state = create_initial_state(phone, text)
            
            # Start workflow
            result = workflow.invoke(initial_state, config=config)
            
            print(f"Workflow started")
            print(f"   Stage: {result.get('current_stage', 'N/A')}")
        
        return jsonify({"status": "processed"}), 200
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Inform user about error
        try:
            supervisor.message_helper.send_message(
                phone, 
                "Something went wrong, can you try again?"
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
    """Debug: View state for a specific phone number"""
    config = {"configurable": {"thread_id": phone}}
    
    try:
        current_state = workflow.get_state(config)
        
        if current_state.values:
            # Remove sensitive info
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
    """Debug: Reset conversation for a specific phone number"""
    # Note: This may work differently with MemorySaver
    # In real implementation, checkpoint may need to be deleted
    return jsonify({
        "status": "reset_requested",
        "phone": phone,
        "note": "Full reset requires checkpoint deletion"
    }), 200


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("MUSIC PRODUCTION BOT")
    print("=" * 60)
    print("Endpoints:")
    print("  POST /webhook     - WhatsApp webhook")
    print("  GET  /health      - Health check")
    print("  GET  /state/<phone> - Debug state")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)