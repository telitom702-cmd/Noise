const { Telegraf } = require("telegraf");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");

const config = require("./config");

const bot = new Telegraf(config.BOT_TOKEN);

const TEMP_DIR = path.join(os.tmpdir(), "noise_bot");

if (!fs.existsSync(TEMP_DIR)) {
    fs.mkdirSync(TEMP_DIR, { recursive: true });
}

// ===============================
// START
// ===============================

bot.start(async (ctx) => {
    await ctx.reply(
        "🎧 Noise Reduction Bot\n\n" +
        "🎵 Audio অথবা 🎬 Video পাঠান।\n\n" +
        "আমি background noise কমিয়ে পরিষ্কার file পাঠাব।\n\n" +
        "Supported:\n" +
        "• MP3\n" +
        "• M4A\n" +
        "• WAV\n" +
        "• OGG\n" +
        "• MP4\n" +
        "• MKV\n" +
        "• অন্যান্য FFmpeg supported format"
    );
});

// ===============================
// HELP
// ===============================

bot.help(async (ctx) => {
    await ctx.reply(
        "🔇 Noise Reduction Bot\n\n" +
        "একটি Audio অথবা Video পাঠান।\n" +
        "Bot automatically noise reduction করবে।"
    );
});

// ===============================
// PROCESS AUDIO
// ===============================

bot.on("audio", async (ctx) => {
    await processMedia(ctx, "audio");
});

// ===============================
// PROCESS VIDEO
// ===============================

bot.on("video", async (ctx) => {
    await processMedia(ctx, "video");
});

// ===============================
// PROCESS DOCUMENT
// ===============================

bot.on("document", async (ctx) => {
    const fileName = ctx.message.document.file_name || "";

    const audioExt = [
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus"
    ];

    const videoExt = [
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".webm",
        ".m4v"
    ];

    const ext = path.extname(fileName).toLowerCase();

    if (audioExt.includes(ext)) {
        await processMedia(ctx, "audio");
        return;
    }

    if (videoExt.includes(ext)) {
        await processMedia(ctx, "video");
        return;
    }

    await ctx.reply(
        "❌ এই file format এখনো support করা হচ্ছে না।"
    );
});

// ===============================
// MAIN PROCESS
// ===============================

async function processMedia(ctx, type) {
    const userId = ctx.from.id;

    let message;
    let inputPath;
    let outputPath;

    try {
        message = await ctx.reply(
            "📥 File গ্রহণ করা হয়েছে...\n\n" +
            "⏳ Download হচ্ছে..."
        );

        let telegramFile;

        if (type === "audio") {
            telegramFile = await ctx.telegram.getFile(
                ctx.message.audio?.file_id ||
                ctx.message.document?.file_id
            );
        } else {
            telegramFile = await ctx.telegram.getFile(
                ctx.message.video?.file_id ||
                ctx.message.document?.file_id
            );
        }

        const fileUrl =
            `https://api.telegram.org/file/bot${config.BOT_TOKEN}/${telegramFile.file_path}`;

        const originalName = getOriginalName(ctx, type);

        const extension =
            path.extname(originalName) ||
            (type === "video" ? ".mp4" : ".mp3");

        const id = `${userId}_${Date.now()}`;

        inputPath = path.join(
            TEMP_DIR,
            `${id}_input${extension}`
        );

        outputPath = path.join(
            TEMP_DIR,
            `${id}_output${type === "video" ? ".mp4" : ".mp3"}`
        );

        await downloadFile(fileUrl, inputPath);

        await ctx.telegram.editMessageText(
            ctx.chat.id,
            message.message_id,
            undefined,
            "🔊 Noise reduction চলছে...\n\n" +
            "⏳ একটু অপেক্ষা করুন..."
        );

        await runFFmpeg(
            inputPath,
            outputPath,
            type
        );

        await ctx.telegram.editMessageText(
            ctx.chat.id,
            message.message_id,
            undefined,
            "📤 Clean file upload হচ্ছে..."
        );

        if (type === "video") {
            await ctx.replyWithVideo(
                {
                    source: outputPath
                },
                {
                    caption:
                        "✅ Noise Reduction Complete\n\n" +
                        `👤 User: ${userId}`
                }
            );
        } else {
            await ctx.replyWithAudio(
                {
                    source: outputPath
                },
                {
                    caption:
                        "✅ Noise Reduction Complete\n\n" +
                        `👤 User: ${userId}`
                }
            );
        }

        await ctx.telegram.deleteMessage(
            ctx.chat.id,
            message.message_id
        );

    } catch (error) {
        console.error(error);

        if (message) {
            try {
                await ctx.telegram.editMessageText(
                    ctx.chat.id,
                    message.message_id,
                    undefined,
                    "❌ Processing failed!\n\n" +
                    "File format বা server সমস্যা হতে পারে।"
                );
            } catch {}
        }
    } finally {
        cleanup(inputPath);
        cleanup(outputPath);
    }
}

// ===============================
// DOWNLOAD
// ===============================

async function downloadFile(url, output) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            `Download failed: ${response.status}`
        );
    }

    const buffer = Buffer.from(
        await response.arrayBuffer()
    );

    fs.writeFileSync(output, buffer);
}

// ===============================
// FFMPEG
// ===============================

function runFFmpeg(input, output, type) {
    return new Promise((resolve, reject) => {

        let args;

        if (type === "video") {

            args = [
                "-y",

                "-i",
                input,

                "-map",
                "0:v:0",

                "-map",
                "0:a:0?",

                "-c:v",
                "copy",

                "-af",
                "afftdn=nf=-25",

                "-c:a",
                "aac",

                "-b:a",
                "128k",

                "-movflags",
                "+faststart",

                output
            ];

        } else {

            args = [
                "-y",

                "-i",
                input,

                "-af",
                "afftdn=nf=-25",

                "-c:a",
                "libmp3lame",

                "-b:a",
                "192k",

                output
            ];
        }

        const ffmpeg = spawn(
            "ffmpeg",
            args
        );

        let errorOutput = "";

        ffmpeg.stderr.on(
            "data",
            (data) => {
                errorOutput += data.toString();
            }
        );

        ffmpeg.on(
            "close",
            (code) => {

                if (code === 0) {
                    resolve();
                } else {
                    console.error(errorOutput);
                    reject(
                        new Error(
                            `FFmpeg exited with code ${code}`
                        )
                    );
                }
            }
        );

        ffmpeg.on(
            "error",
            (error) => {
                reject(error);
            }
        );
    });
}

// ===============================
// ORIGINAL FILE NAME
// ===============================

function getOriginalName(ctx, type) {

    if (type === "audio") {

        if (ctx.message.audio) {
            return (
                ctx.message.audio.file_name ||
                "audio.mp3"
            );
        }

        if (ctx.message.document) {
            return (
                ctx.message.document.file_name ||
                "audio.mp3"
            );
        }
    }

    if (type === "video") {

        if (ctx.message.video) {
            return (
                ctx.message.video.file_name ||
                "video.mp4"
            );
        }

        if (ctx.message.document) {
            return (
                ctx.message.document.file_name ||
                "video.mp4"
            );
        }
    }

    return type === "video"
        ? "video.mp4"
        : "audio.mp3";
}

// ===============================
// CLEANUP
// ===============================

function cleanup(file) {

    if (!file) return;

    try {

        if (fs.existsSync(file)) {
            fs.unlinkSync(file);
        }

    } catch (error) {
        console.error(
            "Cleanup error:",
            error.message
        );
    }
}

// ===============================
// ERROR HANDLER
// ===============================

bot.catch((error) => {
    console.error(
        "Bot error:",
        error
    );
});

// ===============================
// START BOT
// ===============================

bot.launch();

console.log(
    "🎧 Noise Reduction Bot is running..."
);

// Graceful shutdown

process.once(
    "SIGINT",
    () => bot.stop("SIGINT")
);

process.once(
    "SIGTERM",
    () => bot.stop("SIGTERM")
);
