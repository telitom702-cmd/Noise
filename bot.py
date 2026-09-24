import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import noisereduce as nr
import numpy as np
import soundfile as sf

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.errors import MessageNotModified

from config import Config


app = Client(
    "NoiseReducerBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)


# =========================================================
# USER SETTINGS
# =========================================================

user_settings = {}

processing_users = set()


def get_level(user_id):

    return user_settings.get(
        user_id,
        "medium"
    )


# =========================================================
# BUTTONS
# =========================================================

def level_buttons(user_id):

    current = get_level(user_id)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Low" if current == "low" else "Low",
                callback_data="noise_low"
            ),
            InlineKeyboardButton(
                "🟡 Medium" if current == "medium" else "Medium",
                callback_data="noise_medium"
            ),
            InlineKeyboardButton(
                "🔴 High" if current == "high" else "High",
                callback_data="noise_high"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="cancel"
            )
        ]
    ])


# =========================================================
# START
# =========================================================

@app.on_message(filters.command("start"))
async def start_handler(client, message):

    await message.reply_text(
        "🎙️ **Noise Reducer Bot**\n\n"
        "আপনি একটি Audio অথবা Video পাঠান।\n\n"
        "আমি background noise কমিয়ে "
        "পরিষ্কার audio/video ফেরত দেব।\n\n"
        "🔇 Noise Level:\n"
        "🟢 Low = হালকা reduction\n"
        "🟡 Medium = সাধারণ reduction\n"
        "🔴 High = বেশি reduction\n\n"
        "প্রথমে level নির্বাচন করতে পারেন।",
        reply_markup=level_buttons(
            message.from_user.id
        )
    )


# =========================================================
# LEVEL BUTTON
# =========================================================

@app.on_callback_query(
    filters.regex("^noise_(low|medium|high)$")
)
async def level_callback(client, query):

    level = query.data.replace(
        "noise_",
        ""
    )

    user_settings[
        query.from_user.id
    ] = level

    await query.answer(
        f"Noise level: {level}"
    )

    try:

        await query.message.edit_reply_markup(
            level_buttons(
                query.from_user.id
            )
        )

    except MessageNotModified:
        pass


# =========================================================
# CANCEL
# =========================================================

@app.on_callback_query(
    filters.regex("^cancel$")
)
async def cancel_callback(client, query):

    user_id = query.from_user.id

    if user_id in processing_users:

        processing_users.remove(
            user_id
        )

        await query.answer(
            "Processing cancelled."
        )

    else:

        await query.answer(
            "কোনো processing চলছে না।"
        )


# =========================================================
# NOISE REDUCTION
# =========================================================

def reduce_noise(
    input_wav,
    output_wav,
    level
):

    data, rate = sf.read(
        input_wav
    )

    if len(data) == 0:
        raise ValueError(
            "Empty audio"
        )

    # Mono signal for noise estimation
    if data.ndim == 2:

        mono = np.mean(
            data,
            axis=1
        )

    else:

        mono = data

    if level == "low":

        prop = 0.60

    elif level == "high":

        prop = 0.92

    else:

        prop = 0.80

    # Noise sample
    noise_duration = min(
        0.8,
        len(mono) / rate
    )

    noise_samples = max(
        int(rate * noise_duration),
        1
    )

    noise_clip = mono[
        :noise_samples
    ]

    cleaned = nr.reduce_noise(
        y=data,
        sr=rate,
        y_noise=noise_clip,
        stationary=True,
        prop_decrease=prop,
        n_fft=2048,
        win_length=2048,
        hop_length=512
    )

    # Prevent clipping
    peak = np.max(
        np.abs(cleaned)
    )

    if peak > 0.98:

        cleaned = (
            cleaned *
            (0.98 / peak)
        )

    sf.write(
        output_wav,
        cleaned,
        rate,
        subtype="PCM_16"
    )


# =========================================================
# RUN FFMPEG
# =========================================================

async def run_ffmpeg(command):

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:

        raise RuntimeError(
            stderr.decode(
                errors="ignore"
            )[-3000:]
        )


# =========================================================
# AUDIO PROCESSING
# =========================================================

async def process_audio(
    input_file,
    output_file,
    level
):

    temp_wav = (
        input_file.parent /
        "audio.wav"
    )

    cleaned_wav = (
        input_file.parent /
        "cleaned.wav"
    )

    # Convert audio to WAV
    await run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-acodec",
        "pcm_s16le",
        str(temp_wav)
    ])

    # Noise reduction
    reduce_noise(
        temp_wav,
        cleaned_wav,
        level
    )

    # Encode final audio
    await run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(cleaned_wav),
        "-af",
        "highpass=f=70,"
        "lowpass=f=16000,"
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_file)
    ])


# =========================================================
# VIDEO PROCESSING
# =========================================================

async def process_video(
    input_file,
    output_file,
    level
):

    original_audio = (
        input_file.parent /
        "original.wav"
    )

    cleaned_audio = (
        input_file.parent /
        "cleaned.wav"
    )

    # Extract audio
    await run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-acodec",
        "pcm_s16le",
        str(original_audio)
    ])

    # Noise reduction
    reduce_noise(
        original_audio,
        cleaned_audio,
        level
    )

    # Keep original video
    # Replace only audio
    await run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-i",
        str(cleaned_audio),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-shortest",

        str(output_file)
    ])


# =========================================================
# MEDIA HANDLER
# =========================================================

@app.on_message(
    filters.audio |
    filters.video |
    filters.document
)
async def media_handler(
    client,
    message
):

    user_id = message.from_user.id

    if user_id in processing_users:

        await message.reply_text(
            "⏳ আপনার আগের ফাইলটি "
            "এখনও processing হচ্ছে।"
        )

        return

    media = (
        message.audio
        or message.video
        or message.document
    )

    if not media:

        return

    # Size check
    size_mb = (
        media.file_size /
        (1024 * 1024)
    )

    if size_mb > Config.MAX_FILE_SIZE:

        await message.reply_text(
            f"❌ File too large.\n\n"
            f"Maximum: "
            f"{Config.MAX_FILE_SIZE} MB"
        )

        return

    processing_users.add(
        user_id
    )

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="noise_"
        )
    )

    status = None

    try:

        level = get_level(
            user_id
        )

        filename = (
            media.file_name
            or "input"
        )

        extension = (
            Path(filename)
            .suffix
            .lower()
        )

        if not extension:

            extension = ".bin"

        input_file = (
            temp_dir /
            f"input{extension}"
        )

        is_video = (
            message.video is not None
            or extension in [
                ".mp4",
                ".mkv",
                ".mov",
                ".webm",
                ".avi"
            ]
        )

        if is_video:

            output_file = (
                temp_dir /
                "noise_reduced.mp4"
            )

        else:

            output_file = (
                temp_dir /
                "noise_reduced.m4a"
            )

        status = await message.reply_text(
            "📥 **Downloading...**\n"
            "Please wait..."
        )

        # Telegram → temporary file
        await client.download_media(
            message,
            file_name=str(input_file)
        )

        if user_id not in processing_users:

            await status.edit_text(
                "❌ Processing cancelled."
            )

            return

        await status.edit_text(
            "🔇 **Reducing Noise...**\n\n"
            f"Level: `{level}`\n"
            "Please wait..."
        )

        if is_video:

            await process_video(
                input_file,
                output_file,
                level
            )

        else:

            await process_audio(
                input_file,
                output_file,
                level
            )

        if user_id not in processing_users:

            await status.edit_text(
                "❌ Processing cancelled."
            )

            return

        await status.edit_text(
            "📤 **Uploading cleaned file...**"
        )

        if is_video:

            await message.reply_video(
                video=str(output_file),
                caption=(
                    "🎬 **Noise Reduced Video**\n\n"
                    f"🔇 Level: `{level}`"
                ),
                supports_streaming=True
            )

        else:

            await message.reply_audio(
                audio=str(output_file),
                caption=(
                    "🎙️ **Noise Reduced Audio**\n\n"
                    f"🔇 Level: `{level}`"
                )
            )

        await status.delete()

    except Exception as e:

        print(
            "ERROR:",
            repr(e)
        )

        if status:

            try:

                await status.edit_text(
                    "❌ **Processing failed.**\n\n"
                    f"`{str(e)[:1500]}`"
                )

            except Exception:
                pass

    finally:

        processing_users.discard(
            user_id
        )

        # Delete ALL temporary files
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================================================
# START BOT
# =========================================================

if __name__ == "__main__":

    print(
        "🎙️ Noise Reducer Bot Started..."
    )

    app.run()
