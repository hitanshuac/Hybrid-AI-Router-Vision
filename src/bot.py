import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from src.router import classify_and_route
from src.config import TELEGRAM_BOT_TOKEN
from src.context_manager import context_manager

logger = logging.getLogger("bot")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram messages by routing them through the Hybrid AI."""
    user_text = update.message.text
    user_id = update.message.from_user.id
    
    logger.info(f"Telegram Message from {user_id}: {user_text[:50]}...")
    
    # Send a "typing" action to keep the user engaged
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Build prompt with history
    context_prompt = context_manager.build_prompt(user_id, user_text)
    
    # Route the message
    try:
        response, model_used = classify_and_route(context_prompt)
        
        # Save to history
        context_manager.add_message(user_id, "user", user_text)
        context_manager.add_message(user_id, "assistant", response)
        
        full_response = f"🤖 *{model_used}*\n\n{response}"
        
        # Telegram has a 4096 character limit per message
        if len(full_response) > 4000:
            for i in range(0, len(full_response), 4000):
                await update.message.reply_text(full_response[i:i+4000], parse_mode='Markdown')
        else:
            await update.message.reply_text(full_response, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Bot error: {e}")
        await update.message.reply_text(f"⚠️ An error occurred: {str(e)}")

def run_bot():
    """Start the Telegram Bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing! Paste it into secrets/telegram_bot_token.txt")
        return

    logger.info("Starting Hybrid AI Telegram Bot...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(message_handler)
    
    application.run_polling()

if __name__ == "__main__":
    run_bot()
