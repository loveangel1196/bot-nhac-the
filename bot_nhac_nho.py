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

def get_user_mention(user):
    """Lấy định dạng gọi tên chuẩn @username hoặc link profile"""
    if user.username:
        return f"@{user.username}"
    else:
        return f"[{user.full_name}](tg://user?id={user.id})"

async def send_menu(chat_id, context):
    """Gửi bảng menu 3 nút bấm Inline"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 10 Phút", callback_data="time_9"),
            InlineKeyboardButton("🟡 20 Phút", callback_data="time_19"),
            InlineKeyboardButton("🔴 30 Phút", callback_data="time_29")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Nhắc đánh thẻ Bot**\nVui lòng bấm chọn thời gian bên dưới hoặc gõ số (`10`, `20`, `30`). Gõ hoặc bấm `dừng` nếu muốn hủy.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start hoặc /menu"""
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

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng nhắn tin số hoặc chữ 'dừng'"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip().lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    user_mention = get_user_mention(user)
    
    # Xử lý lệnh dừng bằng tin nhắn văn bản
    if text in ["dừng", "dung"]:
        if chat_id in active_reminders:
            reminder_info = active_reminders[chat_id]
            # Kiểm tra xem có đúng là người tạo lịch hoặc có thể cho phép hủy linh hoạt
            reminder_info['task'].cancel()
            del active_reminders[chat_id]
            await update.message.reply_text(
                text=f"🛑 **{user_mention}** đã hủy lịch nhắc nhở thành công!",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Hiện tại nhóm không có lịch nhắc nào đang chạy.")
        return

    minutes_map = {
        "10": (9, "10 phút (nhắc sau 9 phút)"),
        "20": (19, "20 phút (nhắc sau 19 phút)"),
        "30": (29, "30 phút (nhắc sau 29 phút)")
    }
    
    if text in minutes_map:
        minutes, display_text = minutes_map[text]
        
        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()

        # Tạo nút kèm nút Dừng ngay từ đầu
        keyboard = [
            [InlineKeyboardButton("🛑 Dừng nhắc nhở", callback_data=f"stop_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = await update.message.reply_text(
            text=f"✅ **{user_mention}** đã đặt hẹn giờ **{display_text}**!\nBot sẽ nhắc nhở khi đến giờ.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

        task = context.application.create_task(reminder_countdown(chat_id, minutes, user_id, user_mention, context))
        active_reminders[chat_id] = {'task': task, 'user_id': user_id}

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sự kiện bấm nút thời gian"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    user_mention = get_user_mention(user)
    
    chat_id = query.message.chat_id
    data = query.data
    
    if data.startswith("time_"):
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

        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()

        await query.answer("Đã ghi nhận!")
        
        # Gửi kèm nút Dừng
        keyboard = [
            [InlineKeyboardButton("🛑 Dừng nhắc nhở", callback_data=f"stop_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=f"✅ **{user_mention}** đã chọn **{display_text}**!\n⏳ Hệ thống đang đếm ngược...",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

        task = context.application.create_task(reminder_countdown(chat_id, minutes, user_id, user_mention, context))
        active_reminders[chat_id] = {'task': task, 'user_id': user_id}

async def stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi bấm nút Dừng"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    target_user_id_str = data.split("_")[1]
    
    # Chỉ đúng người tạo lịch hoặc bấm nút dừng mới được phép hủy
    if str(user.id) != target_user_id_str:
        await query.answer("⚠️ Bạn không phải là người tạo lịch này nên không thể bấm Dừng!", show_alert=True)
        return

    await query.answer("Đã hủy lịch nhắc!")
    chat_id = query.message.chat_id
    
    if chat_id in active_reminders:
        active_reminders[chat_id]['task'].cancel()
        del active_reminders[chat_id]
        
    await query.edit_message_text(
        text=f"🛑 **{user.full_name} đã hủy lịch nhắc nhở.**",
        parse_mode="Markdown"
    )

async def reminder_countdown(chat_id: int, minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    """Đợi hết thời gian rồi réo tên tài khoản kèm nút OK và nút Dừng"""
    try:
        await asyncio.sleep(minutes * 60)
        
        while True:
            keyboard = [
                [InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")],
                [InlineKeyboardButton("🛑 Dừng nhắc nhở", callback_data=f"stop_{target_user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ {user_mention} **ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!**\nVui lòng bấm OK để hoàn thành hoặc bấm Dừng nếu không muốn nhắc nữa.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info(f"Đã hủy lịch nhắc cho chat_id: {chat_id}")

async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiểm tra đúng người được tag mới cho bấm OK"""
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
        active_reminders[chat_id]['task'].cancel()
        del active_reminders[chat_id]
        
    await query.edit_message_text(
        text=f"👍 **{user.full_name} đã đánh thẻ thành công!** Đã tắt nhắc nhở.",
        parse_mode="Markdown"
    )

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký handlers
    application.add_handler(CommandHandler(["start", "menu"], start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^stop_"))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()
