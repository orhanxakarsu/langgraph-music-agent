# Music Production Agent System

An AI-powered music production system built with LangGraph that orchestrates music generation, cover art creation, and video production through WhatsApp. Users can request custom music, receive AI-generated tracks, select their favorites, and get complete music videos with album artwork.

## What Does This System Do?

This system is a **WhatsApp-based AI music production bot** that:

1. **Generates Custom Music**: Creates original music tracks based on user descriptions using Suno AI
2. **Creates Album Covers**: Generates matching album artwork using Google Gemini's image generation
3. **Produces Music Videos**: Combines music and cover art into shareable video content
4. **Saves Music Personas**: Stores successful music generation parameters for consistent style replication
5. **Manages Conversations**: Maintains context across multiple interactions via WhatsApp

### Example Workflow

```
User: "Create an energetic electronic dance track with 
       female vocals about summer nights"
       
Bot:  "Working on your music! I'll create 2 versions for you..."
      [Generates 2 music tracks via Suno AI]
      
Bot:  "Here are your tracks! 
       Version 1: [link]
       Version 2: [link]
       Which one do you prefer? (1, 2, both, or describe changes)"
       
User: "I like version 1, but make it more upbeat"

Bot:  "Got it! Regenerating with more energy..."
      [Regenerates music]
      
User: "Perfect! Now create a cover for it"

Bot:  [Generates album cover via Gemini]
      "Here's your album cover: [link]"
      
User: "Love it! Can you make a video?"

Bot:  [Combines music + cover into MP4]
      "Your music video is ready: [link]"
      
User: "This style is great, save it as a persona"

Bot:  [Saves generation parameters to database]
      "Persona 'Summer EDM Female' saved! You can use it for future tracks."
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     WhatsApp Webhook Handler                     │
│                       (deneme_workflow.py)                       │
│         Receives messages, manages sessions, serves files        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      System Supervisor                           │
│                    (system_supervisor.py)                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Communication    Task         Music        Delivery        ││
│  │     Agent    →   Planner  →  Selection  →   Agent          ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │   Music    │  │   Cover    │  │   Video    │
    │ Generator  │  │ Generator  │  │ Generator  │
    │(Suno API)  │  │(Gemini API)│  │  (FFmpeg)  │
    └─────┬──────┘  └────────────┘  └────────────┘
          │
          ▼
    ┌────────────┐
    │  Persona   │
    │   Saver    │
    │ (SQLite)   │
    └────────────┘
```

## Core Components

### 1. System Supervisor (`system_supervisor.py`)
The main orchestrator that coordinates all agents:
- **Communication Agent**: Understands user intent, manages conversation flow
- **Task Planner**: Determines what needs to be done (music, cover, video)
- **Music Selection Handler**: Presents options and processes user choices
- **Delivery Agent**: Sends completed content to user

### 2. Music Generation (`suno_ai.py`)
Integrates with Suno AI API:
- Generates 2 music variants per request for user choice
- Supports custom lyrics, instrumental tracks, and style parameters
- Handles remake/remix of existing tracks
- Automatic polling and file download

### 3. Cover Generator (`cover_generator.py`)
Uses Google Gemini for AI artwork:
- Creates minimalist, professional album covers
- Style-aware prompts based on music characteristics
- Supports various image formats

### 4. Video Generator (in `system_supervisor.py`)
Combines music and artwork:
- Uses FFmpeg for video encoding
- Static image + audio merge
- MP4 output format

### 5. Persona Management (`personadb_utils.py`)
SQLite-based style storage:
- **Save Persona**: Store successful music parameters (style, genre, vocal settings)
- **List Personas**: View all saved styles
- **Load Persona**: Apply saved style to new generations
- Database location: `artifacts/databases/personas.db`

### 6. WhatsApp Integration (`whatsapp_helper.py`)
Evolution API wrapper:
- Send/receive text, audio, images, and videos
- Phone number allowlist for access control
- Webhook parsing for incoming messages

## Requirements

### System Requirements
- Python 3.10+
- FFmpeg (for video generation)
- SQLite (included with Python)

### API Services Required
1. **OpenAI API** - For LLM processing
2. **Suno AI API** - For music generation
3. **Google Gemini API** - For image generation
4. **Evolution API** - For WhatsApp messaging (self-hosted or cloud)

## Installation

### 1. Clone and Setup Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd supervisor_agent_for_music_generation

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Install FFmpeg

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows - Download from https://ffmpeg.org/download.html
```

### 3. Get API Keys

#### OpenAI API Key
1. Go to [platform.openai.com](https://platform.openai.com)
2. Sign up or log in
3. Navigate to API Keys section
4. Create new secret key
5. Copy and save the key

#### Suno AI API Key
1. Go to [sunoapi.org](https://sunoapi.org/)
2. Create an account
3. Navigate to dashboard/API section
4. Generate or copy your API key
5. Note: This is a third-party Suno API wrapper service

#### Google Gemini API Key
1. Go to [ai.google.dev](https://ai.google.dev/)
2. Click "Get API key in Google AI Studio"
3. Sign in with Google account
4. Click "Create API key"
5. Select or create a Google Cloud project
6. Copy the generated key

#### Evolution API Setup (WhatsApp)
Evolution API is a self-hosted WhatsApp API solution:

1. **Deploy Evolution API**:
   ```bash
   # Using Docker
   docker run -d \
     --name evolution-api \
     -p 8080:8080 \
     -e AUTHENTICATION_API_KEY=your-api-key \
     atendai/evolution-api
   ```

2. **Create WhatsApp Instance**:
   - Access Evolution API dashboard at `http://your-server:8080`
   - Create new instance
   - Scan QR code with WhatsApp to connect
   - Note down instance name and API key

3. **Configure Webhook**:
   - Set webhook URL to `http://your-server:5000/webhook`
   - Enable message events

For detailed Evolution API setup, see: [Evolution API Documentation](https://doc.evolution-api.com/)

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key

# Suno AI Configuration (from sunoapi.org)
SUNO_AI_API_KEY=your-suno-api-key

# Google Gemini Configuration
GEMINI_API_KEY=your-gemini-api-key

# Evolution API Configuration (WhatsApp)
EVOLUTION_API_URL=http://your-evolution-server:8080
EVOLUTION_API_KEY=your-evolution-api-key
INSTANCE_NAME=your-instance-name

# Server Configuration
SERVER_HOST=your-server-ip-or-domain
SERVER_PORT=5000

# Optional: Restrict access to specific phone numbers (comma-separated)
# Leave empty to allow all numbers
ALLOWED_NUMBERS=905551234567,905559876543
```

### 5. Run the Application

```bash
python deneme_workflow.py
```

The server will start on `http://0.0.0.0:5000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | WhatsApp incoming message handler |
| `/health` | GET | Health check |
| `/state/<phone>` | GET | Debug: View conversation state |
| `/reset/<phone>` | POST | Debug: Reset conversation |
| `/files/music/<filename>` | GET | Serve generated music files |
| `/files/image/<filename>` | GET | Serve generated images |
| `/files/video/<filename>` | GET | Serve generated videos |

## File Structure

```
supervisor_agent_for_music_generation/
├── system_supervisor.py       # Main supervisor and workflow orchestration
├── suno_ai.py                 # Suno API integration for music generation
├── cover_generator.py         # Google Gemini image generation
├── whatsapp_helper.py         # Evolution API WhatsApp wrapper
├── personadb_utils.py         # SQLite persona database management
├── state.py                   # State definitions and initial state factory
├── base_models.py             # Pydantic models for structured outputs
├── user_node.py               # Standalone user communication agent
├── music_generator_supervisor_system.py  # Standalone music supervisor
├── deneme_workflow.py         # Flask webhook server (main entry point)
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (create this)
├── .gitignore                 # Git ignore rules
├── DESCRIPTION.md             # This file
└── artifacts/                 # Generated content (auto-created)
    ├── musics/                # Downloaded music files
    ├── generated_images/      # Generated cover art
    ├── final_videos/          # Combined music videos
    └── databases/             # SQLite databases
        └── personas.db        # Saved personas
```

## Key Features

- **Human-in-the-Loop**: Uses LangGraph's interrupt mechanism for user interactions
- **Stateful Conversations**: MemorySaver maintains conversation state across messages
- **Retry Mechanism**: Automatic retry with configurable limits for API failures
- **Duplicate Detection**: Prevents processing the same message multiple times
- **File Serving**: Built-in static file server for generated content
- **Persona System**: Save and reuse successful music generation styles

## Troubleshooting

### Music generation fails
- Check Suno API key validity at [sunoapi.org](https://sunoapi.org/)
- Verify API credits/quota
- Check network connectivity

### Image generation fails
- Verify Gemini API key at [ai.google.dev](https://ai.google.dev/)
- Check API quotas in Google Cloud Console

### WhatsApp messages not received
- Verify Evolution API webhook URL points to your server
- Check Evolution API instance is connected (QR scanned)
- Ensure firewall allows incoming connections on port 5000

### Video generation fails
- Verify FFmpeg is installed: `ffmpeg -version`
- Check both music and cover files exist before video creation

## License

MIT License
