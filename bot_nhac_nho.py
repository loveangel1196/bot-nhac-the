import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ChatMemberHandler

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Thay thế bằng Token thật do BotFather cấp
TOKEN = "9042194702:AAEuNzFXtzz27GWq3MMDv9BOHZqhFVg4UxM"

# Lưu trữ tiến trình nhắc nhở theo chat_id
active_reminders = {}

async def send_menu(chat_id, context):
    """Hàm gửi menu 3 nút bấm"""
    keyboard = [
        [
            InlineKeyboardButton("10 Phút", callback_data="time_10"),
            InlineKeyboardButton("20 Phút", callback_data="time_20"),
            InlineKeyboardButton("30 Phút", callback_data="time_30")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Nhắc đánh thẻ Bot**\nVui lòng chọn thời gian nhắc nhở:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start"""
    await send_menu(update.effective_chat.id, context)

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tự động gửi menu ngay khi bot được thêm vào nhóm"""
    result = update.my_chat_member
    if result:
        new_member = result.new_chat_member
        if new_member.user.id == context.bot.id and new_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
            chat_id = update.effective_chat.id
            await send_menu(chat_id, context)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sự kiện bấm các nút 10, 20, 30 phút"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    data = query.data
    
    if data == "time_10":
        minutes = 10
    elif data == "time_20":
        minutes = 20
    elif data == "time_30":
        minutes = 30
    else:
        return

    # Hủy lịch nhắc cũ nếu có
    if chat_id in active_reminders:
        active_reminders[chat_id].cancel()

    await query.edit_message_text(
        text=f"✅ Đã đặt hẹn giờ nhắc nhở sau **{minutes} phút** tới!",
        parse_mode="Markdown"
    )

    # Chạy đồng hồ đếm ngược
    task = context.application.create_task(reminder_countdown(chat_id, minutes, context))
    active_reminders[chat_id] = task

async def reminder_countdown(chat_id: int, minutes: int, context: ContextTypes.DEFAULT_TYPE):
    """Đợi đủ thời gian rồi lặp lại thông báo mỗi 5 giây cho đến khi bấm OK"""
    try:
        await asyncio.sleep(minutes * 60)
        while True:
            keyboard = [[InlineKeyboardButton("OK (Đã đánh thẻ)", callback_data="acknowledge_ok")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏰ **ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!**\nVui lòng bấm nút OK bên dưới để xác nhận.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info(f"Đã hủy lịch nhắc cho chat_id: {chat_id}")

async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi bấm nút OK xác nhận"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "acknowledge_ok":
        chat_id = query.message.chat_id
        if chat_id in active_reminders:
            active_reminders[chat_id].cancel()
            del active_reminders[chat_id]
            
        await query.edit_message_text(
            text="👍 **Đã xác nhận!** Đã tắt thông báo nhắc nhở.",
            parse_mode="Markdown"
        )

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^acknowledge_ok$"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()
