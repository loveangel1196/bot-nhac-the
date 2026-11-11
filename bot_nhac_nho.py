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
            InlineKeyboardButton("10 Phút", callback_data="time_9"),  # Trừ 1 phút (còn 9 phút)
            InlineKeyboardButton("20 Phút", callback_data="time_19"), # Trừ 1 phút (còn 19 phút)
            InlineKeyboardButton("30 Phút", callback_data="time_29")  # Trừ 1 phút (còn 29 phút)
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
            # Chờ 1 giây để đảm bảo nhóm đã sẵn sàng nhận tin nhắn từ bot
            await asyncio.sleep(1)
            await send_menu(chat_id, context)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sự kiện bấm các nút thời gian"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    user_name = user.full_name
    
    # Tạo mention dạng @username nếu có, nếu không có username thì dùng link tên hiển thị
    if user.username:
        user_mention = f"@{user.username}"
    else:
        user_mention = f"[{user_name}](tg://user?id={user_id})"
    
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

    await query.answer("Đã ghi nhận yêu cầu của bạn!")
    await query.edit_message_text(
        text=f"✅ **{user_mention}** đã đặt hẹn giờ **{display_text}**!",
        parse_mode="Markdown"
    )

    # Chạy đồng hồ đếm ngược và lưu kèm thông tin user
    task = context.application.create_task(reminder_countdown(chat_id, minutes, user_id, user_mention, context))
    active_reminders[chat_id] = task

async def reminder_countdown(chat_id: int, minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    """Đợi đủ thời gian rồi lặp lại thông báo mỗi 5 giây gọi tên người đó"""
    try:
        # Chờ đợi số phút (đã trừ 1 phút)
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
    """Xử lý khi bấm nút OK (Kiểm tra đúng người bấm mới cho qua)"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    # Tách lấy user_id được phép bấm từ callback_data
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

    # Đăng ký handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()
