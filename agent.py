import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    ChatMessage,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import anthropic, deepgram, elevenlabs, silero

from personas.larry import LARRY_GREETING, LARRY_PROMPT

load_dotenv()

logger = logging.getLogger("telemocker")

TRANSCRIPT_DIR = Path(__file__).parent / "transcripts"
TRANSCRIPT_DIR.mkdir(exist_ok=True)


def _log_turn(filepath: Path, role: str, text: str):
    """Append a single turn to the transcript JSONL file."""
    with open(filepath, "a") as f:
        f.write(
            json.dumps(
                {
                    "role": role,
                    "text": text,
                    "time": datetime.now(timezone.utc).isoformat(),
                }
            )
            + "\n"
        )


async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    logger.info(
        "Call started — room=%s participant=%s",
        ctx.room.name,
        participant.identity,
    )

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # George
    tts_kwargs = {"model": "eleven_turbo_v2_5", "voice_id": voice_id}

    larry = Agent(
        instructions=LARRY_PROMPT,
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=anthropic.LLM(model="claude-haiku-4-5-20251001"),
        tts=elevenlabs.TTS(**tts_kwargs),
    )

    session = AgentSession()

    transcript_path = (
        TRANSCRIPT_DIR
        / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{ctx.room.name}.jsonl"
    )

    @session.on("conversation_item_added")
    def _on_item(event):
        item = event.item
        if not isinstance(item, ChatMessage):
            return
        text = item.text_content
        if not text:
            return
        if item.role == "user":
            logger.info("Caller: %s", text)
            _log_turn(transcript_path, "caller", text)
        elif item.role == "assistant":
            logger.info("Larry: %s", text)
            _log_turn(transcript_path, "larry", text)

    await session.start(larry, room=ctx.room)
    await session.say(LARRY_GREETING, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
