import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ChatMemberHandler, MessageHandler, filters

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
            InlineKeyboardButton("10 Phút", callback_data="time_9"),  # Trừ 1 phút (còn 9 phút)
            InlineKeyboardButton("20 Phút", callback_data="time_19"), # Trừ 1 phút (còn 19 phút)
            InlineKeyboardButton("30 Phút", callback_data="time_29")  # Trừ 1 phút (còn 29 phút)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Nhắc đánh thẻ Bot**\nVui lòng chọn thời gian nhắc nhở hoặc nhắn trực tiếp số phút (`10`, `20`, `30`):",
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
            await asyncio.sleep(1)
            await send_menu(chat_id, context)

def get_user_mention(user):
    """Lấy định dạng gọi tên chuẩn @username hoặc link profile"""
    if user.username:
        return f"@{user.username}"
    else:
        return f"[{user.full_name}](tg://user?id={user.id})"

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng nhắn trực tiếp số 10, 20 hoặc 30 lên nhóm"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    user_mention = get_user_mention(user)
    
    minutes_map = {
        "10": (9, "10 phút (nhắc sau 9 phút)"),
        "20": (19, "20 phút (nhắc sau 19 phút)"),
        "30": (29, "30 phút (nhắc sau 29 phút)")
    }
    
    if text in minutes_map:
        minutes, display_text = minutes_map[text]
        
        # Hủy lịch nhắc cũ của nhóm nếu có
        if chat_id in active_reminders:
            active_reminders[chat_id].cancel()

        # Gửi tin nhắn xác nhận kèm nút OK chính chủ
        keyboard = [[InlineKeyboardButton("OK (Đã đánh thẻ)", callback_data=f"ok_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            text=f"✅ **{user_mention}** đã đặt hẹn giờ **{display_text}**!\nBot sẽ nhắc nhở khi đến giờ.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

        # Chạy đồng hồ đếm ngược
        task = context.application.create_task(reminder_countdown(chat_id, minutes, user_id, user_mention, context))
        active_reminders[chat_id] = task

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sự kiện khi bấm các nút thời gian"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    user_mention = get_user_mention(user)
    
    chat_id = query.message.chat_id
    data = query.data
    
    if data == "time_9":
        minutes = 9
        display_text = "10 phút (nhắc sau 9 phút)"
    elif data == "time_19":
        minutes = 19
        display_text = "20 phút (nhắc sau 19 phút)"
    elif data == "time_29":
        minutes = 29
        display_text = "30 phút (nhắc sau 29 phút)"
    else:
        return

    # Hủy lịch nhắc cũ của nhóm nếu có
    if chat_id in active_reminders:
        active_reminders[chat_id].cancel()

    await query.answer("Đã ghi nhận yêu cầu!")
    await query.edit_message_text(
        text=f"✅ **{user_mention}** đã đặt hẹn giờ **{display_text}**!",
        parse_mode="Markdown"
    )

    # Chạy đồng hồ đếm ngược
    task = context.application.create_task(reminder_countdown(chat_id, minutes, user_id, user_mention, context))
    active_reminders[chat_id] = task

async def reminder_countdown(chat_id: int, minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    """Đợi đủ thời gian rồi lặp lại thông báo mỗi 5 giây, tag thẳng tài khoản Telegram"""
    try:
        await asyncio.sleep(minutes * 60)
        
        while True:
            keyboard = [[InlineKeyboardButton("OK (Đã đánh thẻ)", callback_data=f"ok_{target_user_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ {user_mention} **ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!**\nVui lòng bấm nút OK bên dưới để xác nhận.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info(f"Đã hủy lịch nhắc cho chat_id: {chat_id}")

async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi bấm nút OK (Chỉ đúng người được tag mới bấm được)"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    target_user_id_str = data.split("_")[1]
    
    if str(user.id) != target_user_id_str:
        await query.answer("⚠️ Bạn không phải là người đặt lịch này nên không thể bấm OK!", show_alert=True)
        return

    await query.answer()
    chat_id = query.message.chat_id
    
    if chat_id in active_reminders:
        active_reminders[chat_id].cancel()
        del active_reminders[chat_id]
        
    await query.edit_message_text(
        text=f"👍 **Đã xác nhận hoàn thành!** Đã tắt thông báo nhắc nhở.",
        parse_mode="Markdown"
    )

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký các handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()
