import os
import re
import shutil
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

MAX_BYTES = 45 * 1024 * 1024

URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|instagram\.com)/\S+",
    re.IGNORECASE,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام 👋\n"
        "لینک عمومی ویدیوی YouTube یا Instagram را بفرست."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    match = URL_RE.search(text)

    if not match:
        await update.message.reply_text(
            "لطفاً یک لینک معتبر YouTube یا Instagram بفرست."
        )
        return

    url = match.group(0)

    status_message = await update.message.reply_text(
        "⏳ در حال دانلود و آماده‌سازی ویدیو..."
    )

    temp_dir = Path(tempfile.mkdtemp(prefix="telegram_dl_"))

    try:
        output_template = str(temp_dir / "%(id)s.%(ext)s")

        options = {
            "outtmpl": output_template,
            "paths": {
                "home": str(temp_dir),
            },
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "max_filesize": MAX_BYTES,
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        video = None

        # مسیر نهایی ثبت‌شده توسط yt-dlp بعد از پردازش
        filepath = info.get("filepath")
        if filepath:
            candidate = Path(filepath)
            if candidate.is_file() and candidate.suffix.lower() in {
                ".mp4", ".mkv", ".webm", ".mov"
            }:
                video = candidate

        # fallback: بررسی فایل‌های نهایی داخل پوشه موقت
        if video is None:
            candidates = [
                item for item in temp_dir.rglob("*")
                if item.is_file()
                and not item.name.endswith(".part")
                and item.suffix.lower() in {
                    ".mp4", ".mkv", ".webm", ".mov"
                }
            ]

            if candidates:
                video = max(
                    candidates,
                    key=lambda item: item.stat().st_size
                )

        # fallback نهایی برای شرایط خاص post-processing
        if video is None:
            prepared = Path(ydl.prepare_filename(info))
            possible = [
                prepared,
                prepared.with_suffix(".mp4"),
            ]

            for candidate in possible:
                if candidate.is_file():
                    video = candidate
                    break

        if video is None or not video.is_file():
            files_found = [
                str(item.name)
                for item in temp_dir.rglob("*")
                if item.is_file()
            ]

            details = ", ".join(files_found) if files_found else "هیچ فایل نهایی پیدا نشد"
            raise RuntimeError(
                f"دانلود انجام شد اما فایل نهایی پیدا نشد: {details}"
            )

        if video.stat().st_size > MAX_BYTES:
            raise RuntimeError(
                "حجم ویدیو برای ارسال به تلگرام زیاد است."
            )

        with video.open("rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption="✅ آماده شد",
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=30,
                pool_timeout=30,
            )

        try:
            await status_message.delete()
        except Exception:
            pass

    except Exception as exc:
        message = str(exc)

        try:
            await status_message.edit_text(
                f"❌ دانلود انجام نشد.\n{message[:700]}"
            )
        except Exception:
            await update.message.reply_text(
                f"❌ دانلود انجام نشد.\n{message[:700]}"
            )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN تنظیم نشده است."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

