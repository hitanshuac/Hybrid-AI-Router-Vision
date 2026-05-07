import logging
import io
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from src.router import classify_and_route
from src.config import TELEGRAM_BOT_TOKEN
from src.state_provider import StateProvider

logger = logging.getLogger("bot")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user_text = update.message.text or update.message.caption or ""
    image_data = None

    # Handle Photo (Multimodal Tier 3)
    if update.message.photo:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        # Get highest resolution photo
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image_data = base64.b64encode(photo_bytes).decode('utf-8')
        logger.info(f"ðŸ“¸ Image received from {user_id}. Routing to Vision Tier...")

    if not user_text and not image_data: return

    logger.info(f"Telegram Request from {user_id}: {user_text[:50]}...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # ðŸŒ Cross-Device Sync: Pull history from StateProvider
    history = StateProvider.get_history(user_id, "default_conv")
    history_context = "\n".join([f"{m['role']}: {m['content']}" for m in history[-5:]])
    full_prompt = f"{history_context}\nuser: {user_text}"

    try:
        response, model_used = classify_and_route(full_prompt, image_data=image_data)
        
        # ðŸ”„ Sync back to StateProvider
        # 🔄 Sync back to StateProvider
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": response})
        StateProvider.sync_history(user_id, "default_conv", history)
        
        # Visual Tags for the user
        tag = "🏠 Local"
        if "Pro" in model_used: tag = "🧠 Pro"
        elif "Flash" in model_used: tag = "⚡ Flash"
        
        full_response = f"*{tag}* ({model_used})\n\n{response}"
        
        if len(full_response) > 4000:
            for i in range(0, len(full_response), 4000):
                await update.message.reply_text(full_response[i:i+4000], parse_mode='Markdown')
        else:
            await update.message.reply_text(full_response, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Bot error: {e}")
        await update.message.reply_text(f"âš ï¸ Error: {str(e)}")

def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing in secrets/telegram_bot_token.txt")
        return

    logger.info("ðŸš€ Starting Native Hybrid Telegram Bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handle Text and Photos
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    run_bot()