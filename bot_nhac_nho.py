import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Thay thế "YOUR_TELEGRAM_BOT_TOKEN" bằng Token thật của bạn do BotFather cấp
TOKEN = "9042194702:AAEuNzFXtzz27GWq3MMDv9BOHZqhFVg4UxM"

# Lưu trữ trạng thái nhắc nhở của từng nhóm/chat để tránh gửi chồng chéo
active_reminders = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gửi tin nhắn kèm bàn phím nút bấm khi người dùng gõ /start"""
    keyboard = [
        [
            InlineKeyboardButton("10 Phút", callback_data="time_10"),
            InlineKeyboardButton("20 Phút", callback_data="time_20"),
            InlineKeyboardButton("30 Phút", callback_data="time_30")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 **Nhắc đánh thẻ Bot**\nVui lòng chọn thời gian nhắc nhở:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_callback(context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sự kiện khi người dùng bấm các nút thời gian"""
    query = context.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    data = query.data
    
    # Xác định số phút dựa vào nút được bấm
    if data == "time_10":
        minutes = 10
    elif data == "time_20":
        minutes = 20
    elif data == "time_30":
        minutes = 30
    else:
        return

    # Hủy lịch nhắc cũ của chat này nếu đang chạy
    if chat_id in active_reminders:
        active_reminders[chat_id].cancel()

    await query.edit_message_text(
        text=f"✅ Đã đặt hẹn giờ nhắc nhở sau **{minutes} phút** tới!",
        parse_mode="Markdown"
    )

    # Đặt lịch đếm ngược thời gian chờ để bắt đầu nhắc nhở
    task = context.application.create_task(reminder_countdown(chat_id, minutes, context))
    active_reminders[chat_id] = task

async def reminder_countdown(chat_id: int, minutes: int, context: ContextTypes.DEFAULT_TYPE):
    """Đợi đủ số phút rồi bắt đầu gửi nhắc nhở liên tục mỗi 5 giây"""
    try:
        # Chuyển đổi phút sang giây để chờ đợi
        await asyncio.sleep(minutes * 60)
        
        # Bắt đầu vòng lặp nhắc nhở mỗi 5 giây cho đến khi có người bấm OK
        while True:
            keyboard = [[InlineKeyboardButton("OK (Đã đánh thẻ)", callback_data="acknowledge_ok")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = await context.bot.send_message(
                chat_id=chat_id,
                text="⏰ **ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!**\nVui lòng bấm nút OK bên dưới để xác nhận.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
            # Lưu lại ID tin nhắn thông báo để xử lý khi bấm OK
            context.bot_data[f"reminder_msg_{chat_id}"] = message.message_id
            
            # Lặp lại sau mỗi 5 giây
            await asyncio.sleep(5)
            
    except asyncio.CancelledError:
        logger.info(f"Đã hủy hẹn giờ cho chat_id: {chat_id}")

async def acknowledge_callback(context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng bấm nút OK để tắt chuông nhắc nhở"""
    query = context.callback_query
    await query.answer()
    
    if query.data == "acknowledge_ok":
        chat_id = query.message.chat_id
        
        # Hủy bỏ tiến trình nhắc nhở lặp lại mỗi 5 giây
        if chat_id in active_reminders:
            active_reminders[chat_id].cancel()
            del active_reminders[chat_id]
            
        await query.edit_message_text(
            text="👍 **Đã xác nhận!** Đã tắt thông báo nhắc nhở.",
            parse_mode="Markdown"
        )

def main():
    # Khởi tạo Bot Application
    application = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký các Handler (Bộ xử lý lệnh và nút bấm)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^acknowledge_ok$"))

    print("Bot đang chạy...")
    # Chạy bot ở chế độ Polling
    application.run_polling()

if __name__ == '__main__':
    main()
