"""LiveKit voice agent for LiveLogic."""

from __future__ import annotations

import logging
import os

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, openai, silero

logger = logging.getLogger(__name__)

REASONER_URL = os.getenv("REASONER_URL", "http://localhost:8000")


async def entrypoint(ctx: JobContext) -> None:
    """LiveKit agent entry point."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    logger.info("Participant connected: %s", participant.identity)

    session_id = participant.identity or "default"

    # TODO: Wire up VoicePipelineAgent with Deepgram STT + Cartesia/OpenAI TTS
    # and integrate with the reasoner via REASONER_URL
    #
    # Pipeline:
    # 1. Deepgram STT (with Search mode + security vocabulary)
    # 2. VAD-based interruption handling → /retract endpoint
    # 3. Filler audio after 1s ("Just a second, calculating...")
    # 4. POST /reason with transcript → get response
    # 5. TTS back to participant

    logger.info("Session ID: %s", session_id)
    logger.info("Reasoner URL: %s", REASONER_URL)
    logger.info("Agent ready. Waiting for voice input...")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
