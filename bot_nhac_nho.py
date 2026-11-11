import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ChatMember
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

def get_reply_keyboard():
    """Tạo bàn phím nút bấm cố định ở khung chat (giống hình mẫu số 2)"""
    keyboard = [
        [KeyboardButton("10 Phút"), KeyboardButton("20 Phút"), KeyboardButton("30 Phút")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def send_menu(chat_id, context):
    """Gửi tin nhắn kèm bàn phím nút bấm cố định"""
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Nhắc đánh thẻ Bot**\nVui lòng chọn thời gian bên dưới:",
        reply_markup=get_reply_keyboard(),
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
    """Xử lý khi người dùng bấm nút bàn phím hoặc gõ số 10, 20, 30"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    user_mention = get_user_mention(user)
    
    # Ánh xạ thời gian (Trừ 1 phút theo yêu cầu trước: 10p -> 9p, v.v.)
    minutes_map = {
        "10 Phút": (9, "10 phút (nhắc sau 9 phút)"),
        "20 Phút": (19, "20 phút (nhắc sau 19 phút)"),
        "30 Phút": (29, "30 phút (nhắc sau 29 phút)"),
        "10": (9, "10 phút (nhắc sau 9 phút)"),
        "20": (19, "20 phút (nhắc sau 19 phút)"),
        "30": (29, "30 phút (nhắc sau 29 phút)")
    }
    
    if text in minutes_map:
        minutes, display_text = minutes_map[text]
        
        # Hủy lịch nhắc cũ của nhóm nếu có
        if chat_id in active_reminders:
            active_reminders[chat_id].cancel()

        # Gửi thông báo xác nhận (KHÔNG có nút OK ở bước này)
        await update.message.reply_text(
            text=f"✅ **{user_mention}** đã đặt hẹn giờ **{display_text}**!\nBot sẽ nhắc nhở khi đến giờ.",
            parse_mode="Markdown",
            reply_markup=get_reply_keyboard()
        )

        # Chạy đồng hồ đếm ngược
        task = context.application.create_task(reminder_countdown(chat_id, minutes, user_id, user_mention, context))
        active_reminders[chat_id] = task

async def reminder_countdown(chat_id: int, minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    """Đợi đủ thời gian rồi lặp lại thông báo kèm nút OK chính chủ"""
    try:
        await asyncio.sleep(minutes * 60)
        
        while True:
            # Nút OK chỉ xuất hiện tại đây khi đến giờ nhắc nhở
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
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()
